"""Attach persistent checkout commands to the selected workstation client."""
from pathlib import Path


def install(client, files):
    for name in ("working_copy.py", "package_work.py"):
        files["/workspace/" + name] = Path(__file__).with_name(name).read_text()
    prefix = ('if __name__ == "__main__":\n'
              '    from working_copy import dispatch as dispatch_working_copy\n'
              '    dispatch_working_copy()\n\n')
    return prefix + client, ("projects.py checkout DIR [FILE|FOLDER/ ...] opens a version-tracked working copy. "
        "projects.py update DIR brings in project changes while keeping local edits. "
        "projects.py commit DIR [FILE ...] files changed tracked files or the explicitly named files, "
        "including new files. Same-file conflicts are reported.\n")
