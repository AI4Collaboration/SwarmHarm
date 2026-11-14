BASH = {'type': 'function', 'name': 'bash',
        'description': 'Run a shell command on your persistent workstation. The working directory is /workspace. Commands have a 30-second limit; each output stream is limited to 64,000 bytes.',
        'parameters': {'type': 'object', 'properties': {'command': {'type': 'string'}},
                       'required': ['command'], 'additionalProperties': False}}
