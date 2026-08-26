def apply_patch(file_path: str, find: str, replace: str) -> bool:
    with open(file_path, "r") as f:
        content = f.read()
    if find not in content:
        return False
    content = content.replace(find, replace, 1)
    with open(file_path, "w") as f:
        f.write(content)
    return True
