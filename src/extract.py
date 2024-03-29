#
import json, os, sys, time

#
import text_utils

# dotenv
import dotenv
dotenv.load_dotenv()

# Azure OpenAI
import openai
openai.api_type = os.getenv("OPENAI_TYPE")
openai.api_base = os.getenv("OPENAI_API_ENDPOINT")
openai.api_key = os.getenv("OPENAI_API_KEY")
openai.api_version = os.getenv("OPENAI_API_VERSION")
OPENAI_CHAT_DEPLOYMENT = os.getenv("OPENAI_CHAT_DEPLOYMENT")
OPENAI_CHAT_DEPLOYMENT_INPUT_MAX_TOKEN_SIZE = int(os.getenv("OPENAI_CHAT_DEPLOYMENT_INPUT_MAX_TOKEN_SIZE"))
OPENAI_CHAT_DEPLOYMENT_OUTPUT_MAX_TOKEN_SIZE = int(os.getenv("OPENAI_CHAT_DEPLOYMENT_OUTPUT_MAX_TOKEN_SIZE"))

# Azure Form Recognizer Document Client
from azure.core.credentials import AzureKeyCredential
from azure.ai.formrecognizer import DocumentAnalysisClient
AZURE_FORM_RECOGNIZER_API_ENDPOINT = os.getenv("AZURE_FORM_RECOGNIZER_API_ENDPOINT")
AZURE_FORM_RECOGNIZER_API_KEY = os.getenv("AZURE_FORM_RECOGNIZER_API_KEY")
document_analysis_client = DocumentAnalysisClient(endpoint=AZURE_FORM_RECOGNIZER_API_ENDPOINT, credential=AzureKeyCredential(AZURE_FORM_RECOGNIZER_API_KEY))

# defining a function to create the prompt
def create_conversation_messages(system_file_name, document_specification_file_name, few_shots_file_name, user_content):
	#
	messages = []
	
	# read system message
	with open(system_file_name, "r") as system_file:
		system_content = system_file.read()
	if document_specification_file_name is not None:
		with open(document_specification_file_name, "r") as document_specification_file:
			document_specification = document_specification_file.read()
		system_content += document_specification
	messages.append({ "role": "system", "content": system_content })

	# read few_shots messages
	if few_shots_file_name is not None:
		with open(few_shots_file_name, "r") as few_shots_file:
			few_shots_messages = [json.loads(line) for line in few_shots_file]
		for few_shots_message in few_shots_messages:
			messages.append(few_shots_message)

	# add user message content
	messages.append({ "role": "user", "content": user_content })

	return messages

# execute chat completion
def execute_chat_completion(system_file_name, document_specification_file_name, few_shots_file_name, user_content):
	# defining the user input and the system message
	messages = create_conversation_messages(system_file_name, document_specification_file_name, few_shots_file_name, user_content)
	# send prompt to OpenAI API and detect 429 error
	execution_success = False
	while not execution_success:
		try:
			response = openai.ChatCompletion.create(
				engine=OPENAI_CHAT_DEPLOYMENT,
				messages=messages,
				temperature=0.7,
				max_tokens=OPENAI_CHAT_DEPLOYMENT_OUTPUT_MAX_TOKEN_SIZE,
				top_p=0.95,
				frequency_penalty=0,
				presence_penalty=0,
				stop=None)
			execution_success = True
		except openai.error.RateLimitError as e:
			print(f"  ** OpenAI API RPM Limit, sleeping for {30} seconds...")
			#print(f"  ** {e}")
			time.sleep(30)
	
	return response.choices[0].message.content


# process pdf to extract text:
# - split docs into sub-docs
# - detect metadata (header/footer/etc.) and remove from text
# - output extracted cleansed text
def process_pdf(documents_folder_name, document_pdf_file_name):
		
	document_pdf_file_path = os.path.join(documents_folder_name,document_pdf_file_name)

	# Form Recognizer Processing:
	# - detect 'static content' like page header / footer / numbers
	# - generate clean full text content witout static content (noise)
	# - break down document into top level paragraphs
	document_json_file_name = document_pdf_file_name.replace(".pdf",".json")
	document_json_file_path = os.path.join(documents_folder_name,document_json_file_name)
	print(f"===\nprocess_pdf({document_pdf_file_name})...")
	if not os.path.exists(document_json_file_path):
		with open(document_pdf_file_path, "rb") as document_pdf_file:
			document_pdf_bytes = document_pdf_file.read()
			print(f"  -> using Azure Form Recognizer layout API to extract document structure and content...")
			poller = document_analysis_client.begin_analyze_document("prebuilt-layout", document_pdf_bytes)
			result = poller.result()
			
			# dump full output of Form Recognizer to JSON file
			with open(document_json_file_path, "w") as document_json_file:
				json.dump(result.to_dict(), document_json_file)

	# load Form Recognizer output from JSON file
	with open(document_json_file_path, "r") as document_json_file:
		result = json.load(document_json_file)

	# extract all paragraphs from Form Recognizer output and track metadata vs content
	document_metadata = set()
	document_metadata_paragraphs = []
	document_content_paragraphs = []
	document_sections_candidates = []
	for paragraph in result['paragraphs']:
		if paragraph['content'].lower().startswith("section "):
			document_sections_candidates.append(paragraph['content'])
		if paragraph['role'] in ["pageFooter","pageHeader","pageNumber"]:
			document_metadata_paragraphs.append({ "role": paragraph['role'], "content": paragraph['content'] })
			document_metadata.add(paragraph['content'])
		else:
			document_content_paragraphs.append({ "role": paragraph['role'], "content": paragraph['content'] })
	
	# metadata (pageHeader,pageFooter,pageNumber)
	document_metadata_file = document_pdf_file_name.replace(".pdf",".metadata.tsv")
	document_metadata_file_path = os.path.join(documents_folder_name,document_metadata_file)
	with open(document_metadata_file_path, "w") as document_metadata_file:
		for document_metadata_paragraph in document_metadata_paragraphs:
			document_metadata_file.write(f"{document_metadata_paragraph['role']}\t{document_metadata_paragraph['content']}\n")
	print(f"  -> metadata items detected: {len(document_metadata_paragraphs)}")
	
	# sections candidates
	document_sections_candidates_file = document_pdf_file_name.replace(".pdf",".sections_candidates.txt")
	document_sections_candidates_file_path = os.path.join(documents_folder_name,document_sections_candidates_file)
	with open(document_sections_candidates_file_path, "w") as document_sections_candidates_file:
		for document_sections_candidate in document_sections_candidates:
			document_sections_candidates_file.write(f"{document_sections_candidate}\n")
	print(f"  -> section candidates detected: {len(document_sections_candidates)}")

	# content (everything else)
	# remove all items in the document_metadata set() from the text content and save clean content to txt
	content = result['content']
	for metadata in document_metadata:
		content = content.replace(metadata,"")
	document_content_file_name = document_pdf_file_name.replace(".pdf",".txt")
	document_content_file_path = os.path.join(documents_folder_name,document_content_file_name)
	with open(document_content_file_path, "w") as document_content_file:
		document_content_file.write(content)
	print(f"  -> metadata items detected and removed from content: {len(document_metadata_paragraphs)}")

	# generate paragraph summary file
	document_paragraphs_file_name = document_pdf_file_name.replace(".pdf",".paragraphs.tsv")
	document_paragraphs_file_path = os.path.join(documents_folder_name,document_paragraphs_file_name)
	with open(document_paragraphs_file_path, "w") as document_paragraphs_file:
		for paragraph in document_content_paragraphs:
			document_paragraphs_file.write(f"{paragraph['role']}\t{paragraph['content']}\n")
	print(f"  -> content paragraphs detected: {len(document_content_paragraphs)}")

	# generate headings candidates summary file
	document_headers_candidates_file_name = document_pdf_file_name.replace(".pdf",".headers_candidates.tsv")
	document_headers_candidates_file_path = os.path.join(documents_folder_name,document_headers_candidates_file_name)
	with open(document_headers_candidates_file_path, "w") as document_headers_candidates_file:
		headers_candidates = 0
		for paragraph in document_content_paragraphs:
			l = len(paragraph['content'])
			if 5 < l <= 50:
				document_headers_candidates_file.write(f"{paragraph['role']}\t{paragraph['content']}\n")
				headers_candidates += 1
	print(f"  -> headers candidates detected: {headers_candidates}")

	# clean up headings candidates summary file
	document_headers_candidates_file_name = document_pdf_file_name.replace(".pdf",".headers_candidates.tsv")
	document_headers_candidates_file_path = os.path.join(documents_folder_name,document_headers_candidates_file_name)
	with open(document_headers_candidates_file_path, "r") as document_headers_candidates_file:
		document_headers_candidates_txt = document_headers_candidates_file.read()
	completion_result = execute_chat_completion('prompts/sectionHeading_cleanser_system_3.txt', None, None, document_headers_candidates_txt)
	document_headers_candidates_clean_file_name = document_pdf_file_name.replace(".pdf",".headers.tsv")
	document_headers_candidates_clean_file_path = os.path.join(documents_folder_name,document_headers_candidates_clean_file_name)
	with open(document_headers_candidates_clean_file_path, "w") as document_headers_candidates_clean_file:
		sections = completion_result.split('===INDEX===\n')[1]
		headers_count = sections.count('\n')
		print(f"  -> headers detected: {headers_count}")
		document_headers_candidates_clean_file.write(sections)

# process text to extract spec structured output
def process_text(documents_folder_name, document_text_file_name):
	# feed txt spec into OpenAI model for extraction process
	print(f"===\nprocess_text({documents_folder_name},{document_text_file_name})...")
	document_text_file_path = os.path.join(documents_folder_name,document_text_file_name)
	with open(document_text_file_path, "r") as document_text_file:
		document_text = document_text_file.read()
		#document_text = text_utils.normalize_text(document_text_file.read())
	document_extract_file_name = document_text_file_name.replace(".txt",".extracted.tsv")
	document_extract_file_path = os.path.join(documents_folder_name,document_extract_file_name)
	with open(document_extract_file_path, "w") as document_extract_file:
		chunks = text_utils.split_doc_text(document_text,OPENAI_CHAT_DEPLOYMENT_INPUT_MAX_TOKEN_SIZE)
		for i,chunk in enumerate(chunks):
			print(f"===\n  -> extracting spec from chunk {i+1}/{len(chunks)} ...\n===")
			specs = execute_chat_completion('prompts/document_type_A_system.txt', 'documents_formats/document_type_A.txt', 'prompts/document_type_A_few_shots.jsonl', chunk)
			print(specs)
			document_extract_file.write(specs)

# main
if __name__ == '__main__':
	
	# location of specs to process
	documents_folder_name = 'documents'

	# extract text from pdf
	documents_pdf_file_names = [f for f in os.listdir(documents_folder_name) if f.endswith(".pdf") or f.endswith(".PDF")]
	for document_pdf_file_name in documents_pdf_file_names:
		process_pdf(documents_folder_name, document_pdf_file_name)
	
	# process text to extract structured spec output
	document_text_file_names = [f for f in os.listdir(documents_folder_name) if f.endswith(".txt")]
	for document_text_file_name in document_text_file_names:
		process_text(documents_folder_name, document_text_file_name)