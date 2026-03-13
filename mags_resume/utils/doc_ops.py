import docx
from docx.shared import Inches
from docx.enum.text import WD_ALIGN_PARAGRAPH
import markdown
from bs4 import BeautifulSoup, NavigableString

def extract_text_from_docx(file_path: str) -> str:
    """Reads all text from a .docx file."""
    doc = docx.Document(file_path)
    full_text = []
    for para in doc.paragraphs:
        full_text.append(para.text)
    return '\n'.join(full_text)

def _process_soup_element(paragraph, element, bold=False, italic=False):
    """Recursively adds runs to a paragraph based on soup tags (b, i, strong, em)."""
    if isinstance(element, NavigableString):
        text = str(element)
        if text:
            run = paragraph.add_run(text)
            run.bold = bold
            run.italic = italic
        return

    for child in element.children:
        is_bold = bold or child.name in ['strong', 'b']
        is_italic = italic or child.name in ['em', 'i']
        _process_soup_element(paragraph, child, bold=is_bold, italic=is_italic)

def save_text_to_docx(text: str, output_path: str):
    """Saves markdown/HTML mixed text to a formatted .docx file."""
    # 1. Convert Markdown (and pass-through HTML) to full HTML structure
    html_content = markdown.markdown(text, extensions=['extra'])
    
    # 2. Parse HTML structure
    soup = BeautifulSoup(html_content, 'html.parser')
    
    doc = docx.Document()
    
    # Set page margins to "Narrow" (0.5 inches)
    section = doc.sections[0]
    section.top_margin = Inches(0.5)
    section.bottom_margin = Inches(0.5)
    section.left_margin = Inches(0.5)
    section.right_margin = Inches(0.5)

    # 3. Traverse HTML top-level elements and create Docx elements
    for tag in soup.find_all(recursive=False):
        # Headings (h1 - h6)
        if tag.name and tag.name.startswith('h') and len(tag.name) == 2 and tag.name[1].isdigit():
            level = int(tag.name[1])
            # add_heading returns a paragraph object
            heading = doc.add_heading(level=level)
            _process_soup_element(heading, tag)
            
            if tag.get('align') == 'center':
                heading.alignment = WD_ALIGN_PARAGRAPH.CENTER

        # Paragraphs <p>
        elif tag.name == 'p':
            p = doc.add_paragraph()
            _process_soup_element(p, tag)
            if tag.get('align') == 'center':
                p.alignment = WD_ALIGN_PARAGRAPH.CENTER

        # Unordered Lists <ul>
        elif tag.name == 'ul':
            for li in tag.find_all('li', recursive=False):
                p = doc.add_paragraph(style='List Bullet')
                _process_soup_element(p, li)
        
        # Ordered Lists <ol>
        elif tag.name == 'ol':
            for li in tag.find_all('li', recursive=False):
                p = doc.add_paragraph(style='List Number')
                _process_soup_element(p, li)

        # Horizontal Rules <hr>
        elif tag.name == 'hr':
            # Add a visual divider line (string of underscores centered)
            p = doc.add_paragraph('_' * 60)
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER

        else:
            # Fallback for text nodes or unknown blocks
            if tag.name:
                p = doc.add_paragraph()
                _process_soup_element(p, tag)
    
    doc.save(output_path)