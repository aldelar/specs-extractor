#
import json, os, sys

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

# read SYSTEM_MESSAGE from prompt/system_message.txt
with open("prompts/system_message.txt", "r") as system_message_file:
	SYSTEM_MESSAGE = system_message_file.read()

# process pdf to extract text:
# - split docs into sub-docs
# - detect metadata (header/footer/etc.) and remove from text
# - output extracted cleansed text
def process_pdf(specs_folder_name, spec_pdf_file_name):
		
	spec_pdf_file_path = os.path.join(specs_folder_name,spec_pdf_file_name)

	# Form Recognizer Processing:
	# - detect 'static content' like page header / footer / numbers
	# - generate clean full text content witout static content (noise)
	# - break down document into top level paragraphs
	spec_json_file_name = spec_pdf_file_name.replace(".pdf",".json")
	spec_json_file_path = os.path.join(specs_folder_name,spec_json_file_name)
	if not os.path.exists(spec_json_file_path):
		print(f"===\nprocess_pdf({specs_folder_name},{spec_pdf_file_name})...")
		with open(spec_pdf_file_path, "rb") as spec_pdf_file:
			spec_pdf_bytes = spec_pdf_file.read()
			print(f"  -> using Azure Form Recognizer layout API to extract document structure and content...")
			poller = document_analysis_client.begin_analyze_document("prebuilt-layout", spec_pdf_bytes)
			result = poller.result()
			
			# dump full output of Form Recognizer to JSON file
			with open(spec_json_file_path, "w") as spec_json_file:
				json.dump(result.to_dict(), spec_json_file)
			
			# extract all paragraphs from Form Recognizer output and track metadata vs content
			document_metadata = set()
			document_metadata_paragraphs = []
			document_content_paragraphs = []
			for paragraph in result.paragraphs:
				if paragraph.role in ["title","pageFooter","pageHeader""pageNumber"]:
					document_metadata_paragraphs.append({ "role": paragraph.role, "content": paragraph.content })
					document_metadata.add(paragraph.content)
				else:
					document_content_paragraphs.append({ "role": paragraph.role, "content": paragraph.content })
			document_metadata_file = spec_pdf_file_name.replace(".pdf",".metadata.tsv")
			document_metadata_file_path = os.path.join(specs_folder_name,document_metadata_file)
			with open(document_metadata_file_path, "w") as document_metadata_file:
				for document_metadata_paragraph in document_metadata_paragraphs:
					document_metadata_file.write(f"{document_metadata_paragraph['role']}\t{document_metadata_paragraph['content']}\n")

			# remove all items in the document_metadata set() from the text content and save clean content to txt
			content = result.content
			for metadata in document_metadata:
				content = content.replace(metadata,"")
			spec_content_file_name = spec_pdf_file_name.replace(".pdf",".txt")
			spec_content_file_path = os.path.join(specs_folder_name,spec_content_file_name)
			with open(spec_content_file_path, "w") as spec_content_file:
				spec_content_file.write(content)
			print(f"  -> metadata items detected and removed from content: {len(document_metadata_paragraphs)}")

			# generate paragraph summary file
			spec_paragraphs_file_name = spec_pdf_file_name.replace(".pdf",".paragraphs.tsv")
			spec_paragraphs_file_path = os.path.join(specs_folder_name,spec_paragraphs_file_name)
			with open(spec_paragraphs_file_path, "w") as spec_paragraphs_file:
				for paragraph in document_content_paragraphs:
					spec_paragraphs_file.write(f"{paragraph['role']}\t{paragraph['content']}\n")
			print(f"  -> content paragraphs detected: {len(document_content_paragraphs)}")

# defining a function to create the prompt from the system message and the conversation messages
def create_conversation_prompt(system_message, messages):
    prompt = system_message
    for message in messages:
        prompt += f"\n<|im_start|>{message['sender']}\n{message['text']}\n<|im_end|>"
    prompt += "\n<|im_start|>assistant\n"
    return prompt

# extract specs from doc
def text_to_specs(doc_text):
	# defining the user input and the system message
	system_message = f"<|im_start|>system\n{SYSTEM_MESSAGE}\n<|im_end|>"
	messages = [{"sender": "user", "text": doc_text}]
	prompt = create_conversation_prompt(system_message, messages)
	#print(f"Prompt:\n{prompt}")
	response = openai.Completion.create(
		engine=OPENAI_CHAT_DEPLOYMENT,
		prompt=prompt,
		temperature=0.7,
		max_tokens=OPENAI_CHAT_DEPLOYMENT_OUTPUT_MAX_TOKEN_SIZE,
		top_p=0.95,
		frequency_penalty=0,
		presence_penalty=0,
		stop=['<|im_end|>']
	)
	return response['choices'][0]['text']

# process text to extract spec structured output
def process_text(specs_folder_name, spec_text_file_name):
	# feed txt spec into OpenAI model for extraction process
	print(f"===\nprocess_text({specs_folder_name},{spec_text_file_name})...")
	spec_text_file_path = os.path.join(specs_folder_name,spec_text_file_name)
	with open(spec_text_file_path, "r") as spec_text_file:
		spec_text = spec_text_file.read()
		#spec_text = normalize_text(spec_text_file.read())
	spec_extract_file_name = spec_text_file_name.replace(".txt",".extracted.txt")
	spec_extract_file_path = os.path.join(specs_folder_name,spec_extract_file_name)
	with open(spec_extract_file_path, "w") as spec_extract_file:
		chunks = text_utils.split_doc_text(spec_text,OPENAI_CHAT_DEPLOYMENT_INPUT_MAX_TOKEN_SIZE)
		for i,chunk in enumerate(chunks):
			print(f"  -> extracting spec from chunk #'{i}/{len(chunks)}'...\n===\n")
			specs = text_to_specs(f"Construction Document:\n{chunk}")
			print(specs)
			spec_extract_file.write(specs)

# main
if __name__ == '__main__':
	
	# location of specs to process
	specs_folder_name = 'specs'

	# extract text from pdf
	specs_pdf_file_names = [f for f in os.listdir(specs_folder_name) if f.endswith(".pdf") or f.endswith(".PDF")]
	for spec_pdf_file_name in specs_pdf_file_names:
		process_pdf(specs_folder_name, spec_pdf_file_name)
	
	# process text to extract structured spec output
	spec_text_file_names = [f for f in os.listdir(specs_folder_name) if f.endswith(".txt")]
	for spec_text_file_name in spec_text_file_names:
		process_text(specs_folder_name, spec_text_file_name)