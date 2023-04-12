"""Welcome to Pynecone! This file outlines the steps to create a basic app."""

from pcconfig import config
import pynecone as pc
from newspaper import Article
import time
import fitz
import openai
import json
import uuid
import sys
import glob
import os
from fastapi.responses import FileResponse
from fastapi import HTTPException
from .text_to_pdf import PDFCreator
import threading
from natsort import natsorted

# Set up your OpenAI API key
openai.api_key = os.getenv('OPENAI_API_KEY')

filename = f"{config.app_name}/{config.app_name}.py"

PDF_UPLOAD_MESSAGE: str = "Drag and drop your Résumé or CV PDF"
UPLOAD_DIR: str = ".web/public/{}"
SESSION_IDS = set()
FILE_TYPES = ['pdf', 'txt']
SAMPLE_LETTER = open('./sample_letter.txt') if os.path.exists('sample_letter.txt') else None

def get_prompt(resume_text, job_posting_text):
  prompt_files = natsorted(glob.glob('./prompts/*_v*.txt'), key=lambda x: x.lower())
  return open(prompt_files[-1]).read().format(resume_text=resume_text, job_posting_text=job_posting_text)
       

def set_interval(func, sec):
    def func_wrapper():
        set_interval(func, sec)
        func()
    t = threading.Timer(sec, func_wrapper)
    t.start()
    return t

class State(pc.State):
    """The app state."""

    # The image to show.
    upload_file_name: str = ""
    uploaded_pdf: str = ""
    session_id: str = str(uuid.uuid1())
    job_posting_url: str = ""
    pdf_upload_message: str = PDF_UPLOAD_MESSAGE
    is_upload_loading: bool = False
    is_generate_loading: bool = False
    cover_letter: str = ""
    show_cover_letter: bool = False
    download_pdf_href: str = f"http://localhost:8000/download/pdf/{session_id}"
    download_txt_href: str = f"http://localhost:8000/download/txt/{session_id}"
    generated_pdf: str = ""
    generated_txt: str = ""

    def set_job_posting_url(self, text):
      self.job_posting_url = text

    def set_generate_loading(self):
      self.is_generate_loading = True

    def set_generate_not_loading(self):
      self.is_generate_loading = False

    def set_upload_loading(self):
      self.is_upload_loading = True

    def set_upload_not_loading(self):
      self.is_upload_loading = False

    def toggle_modal(self):
      self.show_cover_letter = not self.show_cover_letter

    @pc.var
    def get_upload_message(self):
      return self.upload_file_name or PDF_UPLOAD_MESSAGE

    async def handle_pdf_upload(self, file: pc.UploadFile):
      SESSION_IDS.add(self.session_id)

      self.set_upload_loading()
      if file.content_type == 'application/pdf':
        upload_file_data = await file.read()

        # Save the file.
        self.uploaded_pdf = UPLOAD_DIR.format(f'{self.session_id}_resume_or_cv.pdf')
        with open(self.uploaded_pdf, "wb") as f:
          f.write(upload_file_data)

        # Update the PDF var
        self.upload_file_name = file.filename
        
      # time.sleep(5)
      self.set_upload_not_loading()

    def generate(self):
      try:
        # extract resume/cv
        print(f'Extracting {self.uploaded_pdf}...')
        doc = fitz.open(self.uploaded_pdf)
        resume_text = ""
        for page in doc:
          resume_text += page.get_text()

        # extract job posting
        print(f'Parsing {self.job_posting_url}...')
        article = Article(self.job_posting_url)
        article.download()
        article.parse()
        job_posting_text = article.text

        # call LLM
        prompt = get_prompt(resume_text, job_posting_text)
        completion = openai.ChatCompletion.create(
          model="gpt-3.5-turbo",
          temperature=0.,
          messages=[
            {
              "role": "system",
              "content": "You are a helpful assistant that writes cover letters for job applicants."
            },
            {
              "role": "user", 
              "content": f"{prompt}"
            }
          ]
        )

        # print(SAMPLE_LETTER)
        # self.cover_letter = SAMPLE_LETTER
        # assert self.cover_letter != None

        self.cover_letter = completion.choices[0].message.content
        self.toggle_modal()
        self.build_files()
      except Exception as e:
        print(e)
        pass

    def build_files(self):
      self.generated_txt = UPLOAD_DIR.format(f'{self.session_id}_cover_letter.txt')
      with open(self.generated_txt, 'w') as txt_f:
        txt_f.write(self.cover_letter)

      self.generated_pdf = UPLOAD_DIR.format(f'{self.session_id}_cover_letter.pdf')
      PDFCreator(self.generated_txt, self.generated_pdf).generate()
  
      print(self.generated_pdf, self.generated_txt)


def index() -> pc.Component:
    return pc.center(
      pc.vstack(
        pc.heading("CoverLetter.ai", font_size="2em"),
        pc.box("Write perfect cover letters with AI 🤖"),
        pc.input(
          on_blur=State.set_job_posting_url, 
          # type_='url',
          placeholder="Paste the URL of the job posting...",
        ),
        pc.vstack(
          pc.upload(
            pc.vstack(
              pc.button(
                "Select File",
                color='grey',
                bg="white",
                border=f"1px solid grey",
              ),
              pc.text(State.get_upload_message, font_size="1em", color='lightgrey'),
            ),
            padding="0.5em",
            multiple=False,
            max_size=5 * 1024 * 1024,
            accept=['application/pdf'],
            # on_mouse_out=lambda: State.handle_pdf_upload(pc.upload_files()),
          ),
          pc.spacer(),
          pc.button(
            'Upload',
            color_scheme='blue',
            variant='outline',
            size='sm',
            is_loading=State.is_upload_loading,
            on_click=lambda: State.handle_pdf_upload(pc.upload_files()),
          ),
          padding="0.5em",
          border="2px dotted",
          width='100%',
        ),
        pc.button(
          'Generate!',
          color_scheme='blue',
          size='lg',
          on_click=[State.set_generate_loading, State.generate, State.set_generate_not_loading],
          is_loading=State.is_generate_loading,
          width='100%',
          is_disabled=(State.job_posting_url == '') and (State.upload_file_name == ''),
        ),
        # pc.text('upload_file_name:', State.upload_file_name, font_size="0.35em"),
        # pc.text('job_posting_url:', State.job_posting_url, font_size="0.35em"),
        # pc.text('is_generate_loading:', State.is_generate_loading, font_size="0.35em"),
        # pc.text('pdf_upload_message:', State.get_upload_message, font_size="0.35em"),
        pc.modal(
          pc.modal_overlay(
            pc.modal_content(
              pc.modal_header("Cover Letter"),
              pc.modal_body(pc.markdown(State.cover_letter), style={'white-space': 'pre-line'}),
              pc.modal_footer(
                pc.link(
                  pc.button("Download TXT", color_scheme='blue', variant='outline'),
                  href=State.download_txt_href,
                  download=True,
                  style={'margin-right': '1em'}
                ),
                pc.link(
                  pc.button("Download PDF", color_scheme='red', variant='outline'),
                  href=State.download_pdf_href,
                  download=True,
                  style={'margin-right': '1em'}
                ),
                pc.button("Close", on_click=State.toggle_modal, color_scheme='red')
              ),
            )
          ),
          is_open=State.show_cover_letter,
          is_centered=True,
          size='6xl',
        ),
        spacing="1.5em",
        font_size="2em",
      ),
      padding_top="10%",
    )

# Add state and page to the app.
app = pc.App(state=State)
app.add_page(index)

@app.api.get("/download/{file_type}/{session_id}")
async def download_letter(file_type: str, session_id: str):
  if session_id in SESSION_IDS or file_type not in FILE_TYPES:
    file_path = UPLOAD_DIR.format(f'{session_id}_cover_letter.{file_type}')
    return FileResponse(path=file_path, media_type=f'application/{file_type}', filename=f'Cover Letter.{file_type}')
  else:
    raise HTTPException(status_code=404, detail="File not found") 

def clean():
  print('Cleaning...')
  paths = glob.glob(UPLOAD_DIR.format('*.pdf')) + glob.glob(UPLOAD_DIR.format('*.txt'))
  for path in paths:
    id = path.split(os.path.sep)[-1].split('_')[0]
    if id not in SESSION_IDS:
      os.remove(path)

clean()
app.compile()