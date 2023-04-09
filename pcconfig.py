import pynecone as pc

config = pc.Config(
    app_name="cover_letter_ai",
    db_url="sqlite:///pynecone.db",
    api_url="http://localhost:8000",
    env=pc.Env.DEV,
)
