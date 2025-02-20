import json
import os
import time

import google.generativeai as genai
from django.http import JsonResponse  # Import HttpResponse
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt

genai.configure(api_key=os.environ["GEMINI_API_KEY"])


def upload_to_gemini(file_data, file_name, mime_type="application/pdf"):
    try:
        # convert to BytesIO

        file_object = genai.upload_file(
            convert_to_bytes_io(file_data),
            mime_type=mime_type,
            display_name=file_name
        )
        print(f"Uploaded file '{file_object.display_name}' as: {file_object.uri}")
        return file_object
    except Exception as e:
        print(f"Error uploading to Gemini: {e}")
        return None


def wait_for_files_active(files):
    print("Waiting for file processing...")
    for name in (file.name for file in files):
        file = genai.get_file(name)
        while file.state.name == "PROCESSING":
            print(".", end="", flush=True)
            time.sleep(10)
            file = genai.get_file(name)
        if file.state.name != "ACTIVE":
            raise Exception(f"File {file.name} failed to process")
    print("...all files ready")
    print()


def index(request):
    return render(request, 'invoices/index.html')


def convert_to_bytes_io(file):
    from io import BytesIO
    file_data = BytesIO()
    for chunk in file.chunks():
        file_data.write(chunk)
    file_data.seek(0)
    return file_data


@csrf_exempt
def upload_invoice(request):
    if request.method == 'POST':
        try:
            # Directly access the uploaded file
            uploaded_file = request.FILES['file']  # Access the file directly
            file_name = uploaded_file.name
            file_data = uploaded_file.read()  # Read the file content
        except KeyError:
            return JsonResponse({'success': False, 'error': 'No file uploaded.'})
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)})

        gemini_file = upload_to_gemini(uploaded_file, file_name)

        if gemini_file:
            return JsonResponse({
                'success': True,
                'filename': gemini_file.display_name,
                'uri': gemini_file.uri,
                'name': gemini_file.name
            })
        else:
            return JsonResponse({'success': False, 'error': 'Failed to upload to Gemini.'})
    return JsonResponse({'success': False, 'error': 'Invalid request method.'})


@csrf_exempt
def process_invoices(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body.decode('utf-8'))
            gemini_file_data = data['files']
        except (json.JSONDecodeError, KeyError) as e:
            return JsonResponse({'success': False, 'error': 'Invalid request format: ' + str(e)})

        if not gemini_file_data:
            return JsonResponse({'success': False, 'error': 'No invoices uploaded.'})

        generation_config = {
            "temperature": 0.2,
            "top_p": 0.95,
            "top_k": 64,
            "max_output_tokens": 8192,
            "response_mime_type": "text/plain",
        }

        model = genai.GenerativeModel(
            model_name="gemini-2.0-pro-exp-02-05",
            generation_config=generation_config,
        )

        gemini_files = []
        for file_info in gemini_file_data:
            gemini_file = genai.get_file(file_info['name'])
            gemini_files.append(gemini_file)

        wait_for_files_active(gemini_files)

        prompt = """
                  get the lowest price quote and vendor name in json among all the pdfs, here price means final value"
                  " in the pdf , so if company one offers 50, 2 offers 30 and 3 offers 70 output json has the one company"
                  " name with the lowest quote in json {name, price}. Include only single json in the response, "
                  "no extra text. Also find common items among all the pdfs and return it
                  json format:
                    {
                    lowest_vendor: {name, price}, 
                    common_items: list of lowest price of the common item {item_name, price , vendor, 
                    appearance_count})
                    }

                    appearance_count meaning: number of companies offering this item
                  """

        try:
            response = model.generate_content(
                [*gemini_files, prompt]
            )
            try:
                response_text = response.text.strip()
                if response_text.startswith("```json"):
                    response_text = response_text[len("```json"):]
                if response_text.endswith("```"):
                    response_text = response_text[:-len("```")]
                response_text = response_text.strip()

                result = json.loads(response_text)
            except json.JSONDecodeError:
                return JsonResponse({'success': False, 'error': 'Invalid JSON response from Gemini.'})

            return JsonResponse({'success': True, 'result': result})
        except Exception as e:
            print(e)
            return JsonResponse({'success': False, 'error': str(e)})

    return JsonResponse({'success': False, 'error': 'Invalid request method.'})
