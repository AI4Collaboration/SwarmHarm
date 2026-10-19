"""Separate transport checks, never counted among the 64 study epochs."""
import argparse
import asyncio
import os
from dataclasses import asdict
from pathlib import Path

from inspect_ai.model import ChatMessageSystem, ChatMessageUser, ChatMessageTool, GenerateConfig, get_model
from inspect_ai.tool import ToolInfo, ToolParams, ToolParam

import provider


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    os.environ["SWH_LW_OUTPUT"] = str(args.output.resolve())
    for name in ("gpt-6-luna", "gpt-6.1-sol"):
        provider.SCOPE.set(f"preflight/{name}")
        model = get_model("hostcodex/" + name)
        tools = [ToolInfo(name="check_sum", description="Add two integers.",
                          parameters=ToolParams(properties={
                              "a": ToolParam(type="integer"), "b": ToolParam(type="integer")
                          }, required=["a", "b"]))]
        messages = [ChatMessageSystem(content="Use the supplied tool for arithmetic."),
                    ChatMessageUser(content="Use check_sum to add 17 and 25, then give the answer.")]
        first = await model.generate(messages, tools=tools,
                                     config=GenerateConfig(reasoning_effort="high", max_retries=0))
        calls = first.message.tool_calls or []
        assert len(calls) == 1 and calls[0].function == "check_sum", first.completion
        call = calls[0]
        assert call.arguments == {"a": 17, "b": 25}, call.arguments
        messages.extend([first.message, ChatMessageTool(content="42", tool_call_id=call.id, function=call.function)])
        second = await model.generate(messages, tools=tools,
                                      config=GenerateConfig(reasoning_effort="high", max_retries=0))
        assert "42" in second.completion, second.completion
        provider.save(args.output / "preflight" / (name + ".json"), {
            "passed": True, "actual_model": second.model,
            "tool_call": asdict(call), "final": second.completion,
            "reasoning_effort": "high", "counted_in_study": False,
        })
        print(f"PREFLIGHT PASSED {name}", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
