from flask import Flask, render_template
from flask_frozen import Freezer
import os
import sys
import markdown

app = Flask(__name__, template_folder='wiki', static_folder='static')
app.config['FREEZER_DESTINATION'] = 'public'
app.config['FREEZER_RELATIVE_URLS'] = True

freezer = Freezer(app)

CONTENT_DIR = os.path.join(os.path.dirname(__file__), 'wiki', 'content')

def load_md_content(page_name):
    """Load and render a Markdown file for the given page name.
    Returns rendered HTML string, or None if no .md file exists."""
    md_path = os.path.join(CONTENT_DIR, f'{page_name}.md')
    if os.path.exists(md_path):
        with open(md_path, 'r', encoding='utf-8') as f:
            return markdown.markdown(f.read(), extensions=['extra', 'toc'])
    return None

@app.route('/')
def home():
    return render_template('pages/index.html', md_content=load_md_content('index'))

@app.route('/<page_name>')
def render_page(page_name):
    # This matches the iGEM GitLab Pages URL scheme exactly
    return render_template(f'pages/{page_name}.html', md_content=load_md_content(page_name))

if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == "freeze":
        freezer.freeze()
    else:
        port = int(os.environ.get('PORT', 8080))
        app.run(debug=True, host='0.0.0.0', port=port)
