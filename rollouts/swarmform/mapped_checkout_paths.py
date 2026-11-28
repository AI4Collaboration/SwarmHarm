"""Resolve project directory selections against the same listing that pins every download."""
from pathlib import Path

import formation_store as store


def install():
    original_checkout = store.checkout

    def checkout(directory, names):
        if not names:
            return original_checkout(directory, names)
        original_call = store.client_call
        listing = original_call(["list"])
        available = {item["name"] for item in listing["artifacts"]}
        selected = {}
        explicitly_named = set()
        for name in names:
            prefix = name.removesuffix("/")
            store.artifact_path(Path(directory), prefix)
            if name in available and not name.endswith("/"):
                if name in explicitly_named:
                    raise ValueError("Duplicate artifact name")
                explicitly_named.add(name)
                selected[name] = None
                continue
            descendants = [item["name"] for item in listing["artifacts"]
                           if item["name"].startswith(prefix + "/")]
            if not descendants:
                raise ValueError(f"Unknown project directory: {name}" if name.endswith("/")
                                 else f"Unknown artifact: {name}")
            selected.update(dict.fromkeys(descendants))

        def pinned_call(arguments):
            if arguments == ["list"]:
                return listing
            return original_call(arguments)

        store.client_call = pinned_call
        try:
            return original_checkout(directory, list(selected))
        finally:
            store.client_call = original_call

    store.checkout = checkout
