# Installed after the ordinary project store in the socket service only.
_ordinary_apply = apply


class VersionConflict(ValueError):
    pass


def apply(state, request):
    operation = request["operation"]
    if operation == "materialize":
        return _ordinary_apply(state, {**request, "operation": "read"})
    if operation == "write" and "base_version" in request:
        expected = request["base_version"]
        if type(expected) is not int or expected < 0:
            raise ValueError("Base version must be a nonnegative integer")
        name = request["name"]
        current = len(state.get("objects", {}).get(name, []))
        if expected != current:
            raise VersionConflict(f"{name}: expected version {expected}, current version {current}")
    return _ordinary_apply(state, request)
