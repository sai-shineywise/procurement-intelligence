import json
import os
import time

import google.generativeai as genai
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt

genai.configure(api_key=os.environ["GEMINI_API_KEY"])


def upload_to_gemini(file_data, file_name, mime_type="application/pdf"):
    try:
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


@login_required
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
            uploaded_file = request.FILES['file']
            file_name = uploaded_file.name
            file_data = uploaded_file
        except KeyError:
            return JsonResponse({'success': False, 'error': 'No file uploaded.'})
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)})

        gemini_file = upload_to_gemini(file_data, file_name)

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
                request.session['gemini_files'] = [file.name for file in gemini_files]
                request.session['model_name'] = model.model_name
                request.session['display_names'] = [file.display_name for file in gemini_files]
                # Initialize or append to chat history
                if 'chat_history' not in request.session:
                    request.session['chat_history'] = []


            except json.JSONDecodeError:
                return JsonResponse({'success': False, 'error': 'Invalid JSON response from Gemini.'})

            return JsonResponse({'success': True, 'result': result})
        except Exception as e:
            print(e)
            return JsonResponse({'success': False, 'error': str(e)})

    return JsonResponse({'success': False, 'error': 'Invalid request method.'})


@csrf_exempt
def chat_with_model(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body.decode('utf-8'))
            user_message = data['message']
        except (json.JSONDecodeError, KeyError) as e:
            return JsonResponse({'success': False, 'error': 'Invalid request format: ' + str(e)})

        gemini_files_names = request.session.get('gemini_files')
        model_name = request.session.get('model_name')
        display_names = request.session.get('display_names')
        chat_history = request.session.get('chat_history', [])

        if not gemini_files_names or not model_name:
            return JsonResponse(
                {'success': False, 'error': 'No previous processing found. Please upload and process invoices first.'})

        model = genai.GenerativeModel(model_name=model_name)
        gemini_files = []
        for file_name in gemini_files_names:
            gemini_file = genai.get_file(file_name)
            gemini_files.append(gemini_file)

        try:
            display_names_str = ", ".join([f"'{name}'" for name in display_names]) if display_names else ""
            context_prompt = f"The following files were previously uploaded: {display_names_str}.  User question: {user_message}"

            history_prompt = "\n".join([f"{msg['role']}: {msg['content']}" for msg in chat_history])
            full_prompt = f"{history_prompt}\n{context_prompt}" if history_prompt else context_prompt

            response = model.generate_content([*gemini_files, full_prompt])

            response_text = response.text  # Just get the raw text

            chat_history.append({'role': 'You', 'content': user_message})
            chat_history.append({'role': 'Model', 'content': response_text})  # Store raw text
            request.session['chat_history'] = chat_history
            request.session.modified = True

            # Return raw text and history
            return JsonResponse({'success': True, 'response': response_text, 'history': chat_history})
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)})

    return JsonResponse({'success': False, 'error': 'Invalid request method.'})


@csrf_exempt
def clear_chat_history(request):
    if request.method == 'POST':
        if 'chat_history' in request.session:
            del request.session['chat_history']
            request.session.modified = True
        return JsonResponse({'success': True})
    return JsonResponse({'success': False, 'error': 'Invalid request method.'})
