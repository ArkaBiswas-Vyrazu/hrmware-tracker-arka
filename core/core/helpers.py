"""Common Helper Functions"""

import sys

from django.conf import settings
import structlog


def get_traceback(show_locals=True) -> list[dict[str]]:
    """Returns relevant traceback information in JSON Format.

    This function can also be used to debug wherever necessary, 
    you only need to make sure that an exception gets called first.
    
    Reference: https://gitlab.com/-/snippets/2284049
    """

    exc_info = sys.exc_info()

    trace = structlog.tracebacks.extract(
            *exc_info, 
            show_locals=(settings.TRACEBACK_SHOW_LOCALS and show_locals),
            locals_max_string=settings.TRACEBACK_LOCALS_MAX_LENGTH
        )

    for stack in trace.stacks:
        if len(stack.frames) <= 50:
            continue

        half = 50 // 2
        fake_frame = structlog.tracebacks.Frame(
            filename="",
            lineno=-1,
            name=f"Skipped frames: {len(stack.frames) - (2 * half)}",
        )
        stack.frames[:] = [*stack.frames[:half], fake_frame, *stack.frames[-half:]]

    stack_dicts = [
        {
            'exc_type': stack.exc_type,
            'exc_value': stack.exc_value,
            'syntax_error': stack.syntax_error,
            'is_cause': stack.is_cause,
            'frames': [
                {
                    'filename': frame.filename,
                    'lineno': frame.lineno,
                    'name': frame.name,
                    'locals': frame.locals,
                }

                for frame in stack.frames
            ],
        }

        for stack in trace.stacks
    ]

    return stack_dicts
