"""Install directory-scoped work in a mapped or socket workstation client."""
from pathlib import Path


def install(client, files, product):
    files["/workspace/package_work.py"] = Path(__file__).with_name("package_work.py").read_text()
    client = 'if __name__ == "__main__":\n    from package_work import dispatch\n    dispatch()\n\n' + client
    help_text = (f"Package builds: projects.py work software/ {product} -- COMMAND opens the source "
                 "package and that booking product in a private working directory. Successful commands "
                 "save only changed files in the selected package and product, including new source modules. "
                 "Omit the product to work on the package alone.\n")
    return client, help_text
