with open('.github/workflows/engine.yml', 'r') as f:
    content = f.read()

content = content.replace("if: github.ref == 'refs/heads/main'", "if: github.event_name == 'push' && github.ref == 'refs/heads/main'")

with open('.github/workflows/engine.yml', 'w') as f:
    f.write(content)

