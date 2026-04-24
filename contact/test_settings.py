"""
Test settings — overrides only what is needed for the test runner.
Inherits everything else from the main settings module.
"""
from contact.settings import *  # noqa: F401, F403

# Use plain file-based storage so tests never need a staticfiles.json manifest
STATICFILES_STORAGE = "django.contrib.staticfiles.storage.StaticFilesStorage"

# Dummy key so langchain_openai doesn't reject the import
OPENAI_API_KEY = "sk-test-dummy-key-for-ci"

# Force SQLite regardless of any environment variable
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}

# Disable ChromaDB warmup side-effects by pointing to a temp dir
CHROMA_HOST = ""
CHROMA_PERSIST_DIR = "/tmp/chroma_test"

# Speed up password hashing in tests
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.MD5PasswordHasher",
]
