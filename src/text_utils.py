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
import re
def normalize_text(s, sep_token = " \n "):
    s = re.sub(r'\s+',  ' ', s).strip()
    s = re.sub(r". ,","",s)
    # remove all instances of multiple spaces
    s = s.replace("..",".")
    s = s.replace(". .",".")
    s = s.strip()
    return s

# split doc into N sub-documents of less than DOC_CHUNK_MAX_TOKENS each
from transformers import GPT2TokenizerFast
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