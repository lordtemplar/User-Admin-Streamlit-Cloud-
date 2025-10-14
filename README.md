# User Admin (Streamlit Cloud)

This directory contains a cleaned version of the Streamlit application that powers the SPMU user administration console. It is designed to be published on GitHub and deployed directly on [Streamlit Community Cloud](https://streamlit.io/cloud).

## Project layout

- `streamlit_app.py` – Streamlit entry point that wires all tabs together.
- `tab_*.py` – UI tabs for editing users, managing subscriptions, questions, calendars, and deletions.
- `services/` – Shared service helpers for MongoDB operations, calendar updates, package definitions, etc.
- `config.py` – Central configuration loader (reads from Streamlit secrets or environment variables).
- `.streamlit/secrets.toml.example` – Template for the secrets needed in production.
- `requirements.txt` – Minimal runtime dependencies for the app.

## Local development

```bash
cd "User-Admin (Streamlit Cloud)"
python -m venv .venv
.venv\Scripts\activate  # PowerShell: .\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
cp .streamlit/secrets.toml.example .streamlit/secrets.toml  # fill in the real values
streamlit run streamlit_app.py
```

The app expects a MongoDB database with collections named `user_profiles`, `questions`, and `transactions` using the same schema as the current production environment.

## Secrets and configuration

Configuration is pulled from Streamlit secrets first and falls back to environment variables. The following keys are required:

```toml
[mongo]
uri = "mongodb://..."
db_name = "users"
collection = "user_profiles"
questions_collection = "questions"

[api]
base_url = "https://api.spmu.me"
star_predict_url = "https://api.spmu.me/api/api5_star_predict"

[gpt]
url = "https://api.openai.com/v1/chat/completions"
api_key = "sk-..."
```

- For local work add them to `.streamlit/secrets.toml` (the file is ignored by Git).
- On Streamlit Community Cloud open the app dashboard → **Settings** → **Secrets** and paste the TOML block above with the real values.
- Alternatively set environment variables such as `MONGO_URI`, `API_BASE_URL`, `STAR_PREDICT_URL`, `GPT_URL`, and `GPT_API_KEY` when running outside Streamlit.

## Deploying to GitHub and Streamlit Cloud

1. Initialise a Git repository in `User-Admin (Streamlit Cloud)` and push it to GitHub (private repository recommended).
2. In the Streamlit Cloud dashboard click **New app**, connect to the GitHub repository, and choose `streamlit_app.py` as the entry point.
3. Under **Advanced settings → Secrets**, paste the TOML snippet (with production credentials).
4. Optionally set environment variables like `PYTHON_VERSION` or add config via `.streamlit/config.toml` if you need theme overrides.
5. Deploy. Streamlit Cloud will install dependencies from `requirements.txt` and launch the app automatically.

## Git hygiene

- `.gitignore` ensures compiled Python artefacts and secrets stay out of the repository.
- Keep `config.py` free from hard-coded credentials; update only via secrets or environment variables.
- When adding new modules ensure user-facing strings remain ASCII by default unless a language-specific requirement exists.

## Troubleshooting

- **Missing secrets**: The app will raise a clear runtime error if required configuration values are absent.
- **Mongo connectivity issues**: Check IP allowlists and credentials for the MongoDB cluster; ensure TLS options match your deployment.
- **Streamlit Cloud resource limits**: Heavy background tasks (e.g., GPT updates) may benefit from batching or offloading to the backend services already used by the API.
