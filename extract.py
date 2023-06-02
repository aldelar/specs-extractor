#
import json, os, re, sys

# dotenv
import dotenv
dotenv.load_dotenv()

# Azure OpenAI
import openai
from num2words import num2words
from transformers import GPT2TokenizerFast
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

# pdf2txt
from pypdf import PdfReader
def pdf2txt(pdf_file_path,txt_file_path):
	pdf = PdfReader(open(pdf_file_path, "rb"))
	txt = ''
	txt_file = open(txt_file_path, "w")
	for page in pdf.pages:
		txt += page.extract_text()
		txt_file.write(txt)
	txt_file.close()

# normalize_text
def normalize_text(s, sep_token = " \n "):
    s = re.sub(r'\s+',  ' ', s).strip()
    s = re.sub(r". ,","",s)
    # remove all instances of multiple spaces
    s = s.replace("..",".")
    s = s.replace(". .",".")
    s = s.strip()
    return s

# split doc into N sub-documents of less than DOC_CHUNK_MAX_TOKENS each
tokenizer = GPT2TokenizerFast.from_pretrained("gpt2")
def split_doc_text(doc_text,max_tokens=1000):
    doc_chunks = []
    doc_chunk = ""
    for sentence in doc_text.split("."):
        if len(tokenizer.encode(doc_chunk + sentence)) < max_tokens:
            doc_chunk += sentence + "."
        else:
            doc_chunks.append(doc_chunk)
            doc_chunk = sentence + "."
    doc_chunks.append(doc_chunk)
    return doc_chunks


# defining a function to create the prompt from the system message and the conversation messages
def create_prompt(system_message, messages):
    prompt = system_message
    for message in messages:
        prompt += f"\n<|im_start|>{message['sender']}\n{message['text']}\n<|im_end|>"
    prompt += "\n<|im_start|>assistant\n"
    return prompt


# extract specs from doc
def extract_specs(doc_text):
	# defining the user input and the system message
	system_message = f"<|im_start|>system\n{SYSTEM_MESSAGE}\n<|im_end|>"
	messages = [{"sender": "user", "text": doc_text}]
	prompt = create_prompt(system_message, messages)
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

# main
if __name__ == '__main__':
	
	specs_folder_name = 'specs'

	specs_pdf_file_names = [f for f in os.listdir(specs_folder_name) if f.endswith(".pdf") or f.endswith(".PDF")]
	for spec_pdf_file_name in specs_pdf_file_names:

		spec_text_file_name = spec_pdf_file_name.replace(".pdf",".txt")
		spec_pdf_file_path = os.path.join(specs_folder_name,spec_pdf_file_name)

		# convert specs pdfs to texts if texts versions do not exist
		# spec_text_file_path = os.path.join(specs_folder_name,spec_text_file_name)
		# if not os.path.exists(spec_text_file_path):
		# 	print(f"Converting spec '{spec_pdf_file_name}' to text...")
		# 	pdf2txt(spec_pdf_file_path,spec_text_file_path)
		
		# Form Recognizer Processing:
		# - detect 'static content' like page header / footer / numbers
		# - generate clean full text content witout static content (noise)
		# - break down document into top level paragraphs
		spec_json_file_name = spec_pdf_file_name.replace(".pdf",".json")
		spec_json_file_path = os.path.join(specs_folder_name,spec_json_file_name)
		if not os.path.exists(spec_json_file_path):
			print(f"===\nProcessing spec '{spec_pdf_file_name}'...")
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

	if True:
		# feed txt spec into OpenAI model for extraction process
		spec_text_file_names = [f for f in os.listdir(specs_folder_name) if f.endswith(".txt")]
		for spec_text_file_name in spec_text_file_names:
			print(f"Extracting spec from '{spec_text_file_name}'...")
			spec_text_file_path = os.path.join(specs_folder_name,spec_text_file_name)
			with open(spec_text_file_path, "r") as spec_text_file:
				spec_text = spec_text_file.read()
				#spec_text = normalize_text(spec_text_file.read())
			spec_extract_file_name = spec_text_file_name.replace(".txt",".extracted.txt")
			spec_extract_file_path = os.path.join(specs_folder_name,spec_extract_file_name)
			with open(spec_extract_file_path, "w") as spec_extract_file:
				chunks = split_doc_text(spec_text,OPENAI_CHAT_DEPLOYMENT_INPUT_MAX_TOKEN_SIZE)
				for i,chunk in enumerate(chunks):
					print(f"===\nExtracting spec from chunk #'{i}/{len(chunks)}'...\n===\n")
					specs = extract_specs(f"Construction Document:\n{chunk}")
					print(specs)
					spec_extract_file.write(specs)