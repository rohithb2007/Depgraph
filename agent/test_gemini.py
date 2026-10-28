import os


def main():
    """Explicit manual smoke test; importing this module never sends source or makes API calls."""
    if os.environ.get("DEPGRAPH_ENABLE_AI") != "1":
        raise SystemExit("Set DEPGRAPH_ENABLE_AI=1 to explicitly permit a provider request.")
    if not os.environ.get("GEMINI_API_KEY") or not os.environ.get("DEPGRAPH_MODEL"):
        raise SystemExit("GEMINI_API_KEY and DEPGRAPH_MODEL must be configured.")
    from google import genai

    with genai.Client(api_key=os.environ["GEMINI_API_KEY"]) as client:
        response = client.models.generate_content(
            model=os.environ["DEPGRAPH_MODEL"],
            contents="Say hello in one short sentence. Do not mention APIs or code.",
        )
    print(response.text)


if __name__ == "__main__":
    main()
