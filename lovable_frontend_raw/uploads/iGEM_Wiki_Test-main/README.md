# CERNAL iGEM Wiki Repository

Welcome to the CERNAL repository! This project follows the official Python-Flask architecture required by iGEM for building and statically serving your GitHub/GitLab pages via CI/CD.

## Structure
- `static/` -> CSS and JavaScript assets
- `wiki/` -> Layouts
- `wiki/pages/` -> Actual content templates rendered by Flask

## Local Development
To preview the Wiki locally, run:
```bash
pip install -r dependencies.txt
python app.py
```
Then navigate to `http://localhost:8080`.

## Building Static Pages
To freeze the Flask app into static HTML files for deployment (e.g. for GitHub/GitLab pages):
```bash
python app.py freeze
```
The output will be placed in the `public/` folder.