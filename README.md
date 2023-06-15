# specs-extractor

## Use Case

Pattern to process parts of a large PDF document into a predefined specific structured format. The source document is expected to be a combination of 1 to N different sub-documents, some of which may need to be processed to generate a specific target structured output.

## Approach

This sample script illustrates the overall concept of the architecture below. It is by no means complete but provides basic validation that this approach has potential.

The overall tactic here is to bring enough structure understanding to the document to do the most contextually accurate chunking to extract (summarize) specific parts of a document with potnetially customized prompts for each section/part of a document. It's a generic approach which could support multiple use cases for which the source is a large losely formatted document.

One recommendation would be to build as the document structure gets processed a JSON representation of it's structure and store it in a DB like CosmosDB (SQL API) which would then provide easy query capabilities to discover sections/parts of the docs and ask for specific chunks.

Consider a mapping of document section/part type to optimized prompts to process each section (some prompts could be related to entity extractions for instance, some could check against regulations, others reformat content to feed into another system API, etc.)

Demonstrated here:
- Layout API of Form Recognizer (aka FR) to do OCR + Layout analysis and identify based on location on page where document headings are
- some basic parsing code to extract 'section' related info. This is a good candidate for a prompt based approach for a more lose and reliable extraction and where passing the context about the doc format (Ex CSI MasterFormat section codes) would be appropriate.
- Using GPT to take a rough cut of what all paragraphs may be (based on length of line extracted) and asking it to 'fix' the layout by doing automatic pattern detection of heading formats + other formatting
- using prompts to format to a desired output format

Missing in the implementation:
- keeping track of text location and structure into an actual JSON structure
- querying the JSON structure to extract specific sections and then assigning to the right prompt to get the proper desired extraction
- document classifier: could most likely build a simple model with LLMs (describe what doc is about, send first 2 pages and classify) or use embeddings to match first paragraphs against expected doc content (cheaper approach and may be as accurate)

To be considered for extra accuracy:
- system doing analysis of entire document structure and presenting to user to identify issues
- user chatting with system to describe issues and asking to optimize this doc 'index'
- system using default prompt for a section and showcasing output + getting feedback as far as issues / accuracies and re-writing its own prompt to tune to desired effect
- then apply this to entire document

To be considered for cost optimizations:
- FR Read API to detect header/footer and chunk out this data from core document data
- FR Layout API used only on first 2 pages of relevant docs to extract sectionHeading 'candidates' and then ask GPT to build a pattern for these headers, then use that on truncated lines of all extracted content to extract core document structure

## Architecture Overview

![assets/architecture.png](assets/architecture.png)

## Usage

1. Create a 'documents' directory in the root level of this repository and place the PDFs you want to extract in that folder.

2. Optional: Copy the documents_formats/*.template files and customize them as .txt files (one version already available for CSI MasterFormat use case)

3. Optional: Copy the prompts/*.template files and customize them as .txt (one version already available for CSI MasterFormat use case)

4. Copy src/.env.template to src/.env and update the values to match your environment.

5. Run the following commands to setup the environment and run the extraction script:

```bash
conda env create -f conda.yml
conda activate specs-extractor
python src/extract.py
```