"""
 - ,

:
1. LogSection - /
2.  - ,
3.  - ,
4.  - 
5.  -  emoji 
"""

import logging
import re
import time
import unicodedata
from contextlib import contextmanager
from typing import Any, Dict, List, Optional, Union


# ====================  ====================

def normalize_text(text: Optional[str]) -> str:
    """
    ()

     nodes.py  APIProcessor._normalise_name()  DirectionProcessor._normalise_name()

    :
    1. Unicode (NFKD)
    2.  ASCII( ASCII )
    3. 
    4. ,
    5. 

    Args:
        text: 

    Returns:
        

    Example:
        >>> normalize_text("Cafe Munchen")
        'cafe munchen'
        >>> normalize_text("McDonald's #1")
        'mcdonalds 1'
    """
    if not text:
        return ""

    # Unicode (NFKD)
    normalised = unicodedata.normalize("NFKD", text)

    #  ASCII( ASCII )
    ascii_text = normalised.encode("ascii", "ignore").decode("ascii")

    # 
    ascii_text = ascii_text.lower()

    # ,
    ascii_text = re.sub(r"[^a-z0-9]+", " ", ascii_text)

    # 
    return ascii_text.strip()


# ====================  ====================

# (, logging_utils  LogFormatter )
SYMBOLS = {
    # 
    'success': 'OK',
    'error': 'X',
    'warning': 'WARNING',
    'check': 'OK',
    'cross': 'ERROR',

    # 
    'lightning': 'FAST',
    'globe': '',
    'robot': '',
    'chart': 'CHART',
    'star': '',
    'clipboard': 'LIST',
    'hammer': 'BUILD',
    'magnifier': 'SEARCH',
    'target': '',
    'location': '',
    'time': 'TIME',
    'info': 'INFO',

    # 
    'arrow_right': '->',
    'arrow_down': 'v',

    # 
    'tree_mid': '+-',
    'tree_end': '+-',
    'tree_line': '|',
}


def format_duration(seconds: float) -> str:
    """
    

    Examples:
        0.123 -> "0.12s"
        1.5 -> "1.50s"
        65.3 -> "01:05.3"
    """
    if seconds < 60:
        return f"{seconds:05.2f}s"
    else:
        mins = int(seconds // 60)
        secs = seconds % 60
        return f"{mins:02d}:{secs:04.1f}"


def format_data_summary(data: Any, max_length: int = 80, logger_level: Optional[int] = None) -> str:
    """
    ()

     executors._format_value()  operators._format_value_for_log() 

    Args:
        data: 
        max_length: ( 80)
        logger_level: Logger (). DEBUG,

    Returns:
        
    """
    import json
    from .logging_formatter import LogFormatter

    if data is None:
        return "None"

    # Location ( LogFormatter)
    if hasattr(data, '__class__') and data.__class__.__name__ == 'Location':
        #  state.py  Location 
        name = getattr(data, 'name', 'Unknown')
        lat = getattr(data, 'lat', 0.0) or 0.0
        lng = getattr(data, 'lng', 0.0) or 0.0
        return LogFormatter.format_location(name, lat, lng)

    #  origin_location (geocode )
    if isinstance(data, dict) and 'origin_location' in data:
        loc = data['origin_location']
        if hasattr(loc, '__class__') and loc.__class__.__name__ == 'Location':
            name = getattr(loc, 'name', 'Unknown')
            lat = getattr(loc, 'lat', 0.0) or 0.0
            lng = getattr(loc, 'lng', 0.0) or 0.0
            loc_str = LogFormatter.format_location(name, lat, lng)
            locations_count = len(data.get('locations', []))
            return f"{{origin: {loc_str}, locations: {locations_count} items}}"

    # 
    if isinstance(data, list):
        if not data:
            return "[]"
        #  Location 
        if hasattr(data[0], '__class__') and data[0].__class__.__name__ == 'Location':
            names = [getattr(loc, 'name', 'Unknown') for loc in data[:3]]
            names_str = ', '.join(names)
            if len(data) > 3:
                names_str += '...'
            return f"[{len(data)} locations: {names_str}]"
        #  -  JSON 
        try:
            s = json.dumps(data, ensure_ascii=False, indent=None)
            # DEBUG :
            if logger_level is not None and logger_level <= logging.DEBUG:
                return s
            # 
            if len(s) > max_length:
                return s[:max_length] + "..."
            return s
        except:
            # ,
            if len(data) == 1:
                return f"[{format_data_summary(data[0], max_length-2, logger_level)}]"
            return f"List[{len(data)} items]"

    #  -  JSON 
    if isinstance(data, dict):
        if not data:
            return "{}"
        try:
            s = json.dumps(data, ensure_ascii=False, indent=None)
            # DEBUG :
            if logger_level is not None and logger_level <= logging.DEBUG:
                return s
            # 
            if len(s) > max_length:
                return s[:max_length] + "..."
            return s
        except:
            # ,
            keys = list(data.keys())[:3]
            key_str = ', '.join(str(k) for k in keys)
            if len(data) > 3:
                key_str += '...'
            return f"Dict({key_str})"

    # 
    if isinstance(data, str):
        if len(data) <= max_length:
            return data
        # DEBUG :
        if logger_level is not None and logger_level <= logging.DEBUG:
            return data
        return data[:max_length-3] + '...'

    # 
    result = str(data)
    # DEBUG :
    if logger_level is not None and logger_level <= logging.DEBUG:
        return result
    if len(result) > max_length:
        return result[:max_length-3] + '...'
    return result


def format_table(
    headers: List[str],
    rows: List[List[Any]],
    col_widths: Optional[List[int]] = None
) -> str:
    """
    

    Args:
        headers: 
        rows: 
        col_widths: ()

    Returns:
        
    """
    if not rows:
        return ""

    # 
    if col_widths is None:
        col_widths = []
        for i in range(len(headers)):
            max_width = len(headers[i])
            for row in rows:
                if i < len(row):
                    max_width = max(max_width, len(str(row[i])))
            col_widths.append(min(max_width + 2, 40))

    # 
    lines = []

    # 
    header_line = '  '.join(
        headers[i].ljust(col_widths[i])
        for i in range(len(headers))
    )
    lines.append(header_line)
    lines.append('-' * len(header_line))

    # 
    for row in rows:
        row_line = '  '.join(
            str(row[i] if i < len(row) else '').ljust(col_widths[i])
            for i in range(len(headers))
        )
        lines.append(row_line)

    return '\n'.join(lines)


def log_separator(
    logger: logging.Logger,
    level: int = logging.INFO,
    char: str = '=',
    length: int = 80
):
    """
    

    Args:
        logger: Logger 
        level: 
        char: 
        length: 
    """
    logger.log(level, char * length)


def log_box(
    logger: logging.Logger,
    content: str,
    level: int = logging.INFO,
    width: int = 79
):
    """
    ( LogFormatter  Box )

    Args:
        logger: Logger 
        content: 
        level: 
        width: 
    """
    #  LogFormatter  Box ,
    top = LogFormatter.BOX_TOP_LEFT + LogFormatter.BOX_HORIZONTAL * (width - 2) + LogFormatter.BOX_TOP_RIGHT
    bottom = LogFormatter.BOX_BOTTOM_LEFT + LogFormatter.BOX_HORIZONTAL * (width - 2) + LogFormatter.BOX_BOTTOM_RIGHT

    logger.log(level, top)

    # ,
    lines = content.split('\n')
    for line in lines:
        if len(line) <= width - 4:
            padded = line.ljust(width - 4)
            logger.log(level, f'{LogFormatter.BOX_VERTICAL} {padded} {LogFormatter.BOX_VERTICAL}')
        else:
            # 
            for i in range(0, len(line), width - 4):
                chunk = line[i:i + width - 4].ljust(width - 4)
                logger.log(level, f'{LogFormatter.BOX_VERTICAL} {chunk} {LogFormatter.BOX_VERTICAL}')

    logger.log(level, bottom)


@contextmanager
def LogSection(
    logger: logging.Logger,
    title: str,
    level: int = logging.INFO,
    show_duration: bool = True
):
    """
    

    /,

    Usage:
        with LogSection(logger, "NODE 1/5: ROUTE (AgentRouting)"):
            # 
            logger.info("Intent classified: nearby")

    Output:
        +-------------------------------------------------------------+
        | FAST NODE 1/5: ROUTE (AgentRouting)                   [00:01.8s] |
        +-------------------------------------------------------------+
          +- Intent classified: nearby
          +- ...
    """
    start_time = time.time()

    # 
    log_box(logger, f"{SYMBOLS['lightning']} {title}", level)

    try:
        yield
    finally:
        # 
        if show_duration:
            duration = time.time() - start_time
            duration_str = format_duration(duration)
            logger.log(level, f"  {SYMBOLS['check']} Section completed in {duration_str}")


class ProgressLogger:
    """
    

    
    """

    def __init__(self, logger: logging.Logger, total_steps: int, prefix: str = "Step"):
        self.logger = logger
        self.total_steps = total_steps
        self.prefix = prefix
        self.current_step = 0

    def log_step(self, description: str, level: int = logging.INFO):
        """
        

        Args:
            description: 
            level: 
        """
        self.current_step += 1
        progress = f"[{self.prefix} {self.current_step}/{self.total_steps}]"
        self.logger.log(level, f"  {SYMBOLS['tree_mid']} {progress} {description}")

    def log_final_step(self, description: str, level: int = logging.INFO):
        """
        

        Args:
            description: 
            level: 
        """
        self.current_step += 1
        progress = f"[{self.prefix} {self.current_step}/{self.total_steps}]"
        self.logger.log(level, f"  {SYMBOLS['tree_end']} {progress} {description}")


def log_key_value(
    logger: logging.Logger,
    key: str,
    value: Any,
    level: int = logging.INFO,
    indent: int = 2
):
    """
    ()

    Args:
        logger: Logger 
        key: 
        value: 
        level: 
        indent: 
    """
    indent_str = ' ' * indent
    value_str = format_data_summary(value)
    logger.log(level, f"{indent_str}{key}: {value_str}")


def log_api_call(
    logger: logging.Logger,
    api_name: str,
    params: Optional[Dict] = None,
    result: Optional[Any] = None,
    duration: Optional[float] = None,
    level: int = logging.INFO
):
    """
     API 

    Args:
        logger: Logger 
        api_name: API 
        params: ()
        result: ()
        duration: ()
        level: 
    """
    # :  API Call: geocode(Khansa Market) -> (21.45, 39.85) [0.2s]
    msg = f"  {SYMBOLS['globe']} API Call: {api_name}"

    if params:
        param_str = ', '.join(f"{k}={format_data_summary(v, 30)}" for k, v in params.items())
        msg += f"({param_str})"

    if result is not None:
        result_str = format_data_summary(result, 50)
        msg += f" {SYMBOLS['arrow_right']} {result_str}"

    if duration is not None:
        duration_str = format_duration(duration)
        msg += f" [{duration_str}]"

    logger.log(level, msg)


def log_evaluation_scores(
    logger: logging.Logger,
    scores: Dict[int, float],
    options: List[str],
    predicted_idx: int,
    distances: Optional[Dict[int, float]] = None,
    level: int = logging.INFO
):
    """
    ()

    Args:
        logger: Logger 
        scores: {: }
        options: 
        predicted_idx: 
        distances: ()
        level: 
    """
    logger.log(level, f"  {SYMBOLS['tree_mid']} {SYMBOLS['target']} Scores:")

    for idx in sorted(scores.keys()):
        option_text = options[idx] if idx < len(options) else f"Option {idx}"
        score = scores[idx]

        # 
        line = f"    Option {idx}: {score:.3f}"

        # 
        if distances and idx in distances:
            dist = distances[idx]
            if dist < 1:
                dist_str = f"{dist*1000:.0f}m"
            else:
                dist_str = f"{dist:.1f}km"
            line += f" ({dist_str})"

        # 
        if idx == predicted_idx:
            line += f" {SYMBOLS['arrow_right']} PREDICTED"

        logger.log(level, line)


def log_workflow_summary(
    logger: logging.Logger,
    duration: float,
    llm_calls: int,
    api_calls: int,
    result: Dict[str, Any],
    level: int = logging.INFO
):
    """
    

    Args:
        logger: Logger 
        duration: 
        llm_calls: LLM 
        api_calls: API 
        result: 
        level: 
    """
    duration_str = format_duration(duration)

    log_separator(logger, level)
    logger.log(
        level,
        f"{SYMBOLS['check']} WORKFLOW COMPLETED | Total: {duration_str} | "
        f"LLM: {llm_calls} calls | Google API: {api_calls} calls"
    )
    log_separator(logger, level)

    # 
    logger.log(level, "Result:")
    log_key_value(logger, "  - Intent", result.get("intent"), level)
    log_key_value(logger, "  - Measure", result.get("measure"), level)
    log_key_value(logger, "  - Predicted", result.get("predicted_option"), level)

    if result.get("correct_answer") is not None:
        correct = result.get("correct_answer")
        predicted = result.get("predicted_option")
        log_key_value(logger, "  - Correct", correct, level)

        if predicted == correct:
            logger.log(level, f"  - Status: {SYMBOLS['check']} MATCH")
        else:
            logger.log(level, f"  - Status: {SYMBOLS['cross']} MISMATCH")


# ==================== ( LogFormatter) ====================

from .logging_formatter import LogFormatter


def log_phase(
    logger: logging.Logger,
    phase_name: str,
    details: Optional[Dict[str, Any]] = None,
    duration: Optional[float] = None,
    emoji: str = "",
    level: int = logging.INFO
):
    """
    ()

    Args:
        logger: Logger 
        phase_name: 
        details: 
        duration: ()
        emoji: emoji 
        level: 

    Example:
        log_phase(logger, "Planning", {"concepts": 3, "steps": 5}, 10.4, "LIST")
    """
    # 
    title = phase_name
    if duration is not None:
        duration_str = format_duration(duration)
        title += f" ({duration_str})"

    # 
    header = LogFormatter.section_header(f"{emoji} {title}" if emoji else title)
    for line in header.split('\n'):
        logger.log(level, line)

    # 
    if details:
        for key, value in details.items():
            logger.log(level, f"{LogFormatter.BOX_VERTICAL} {key}: {format_data_summary(value)}")

    # 
    logger.log(level, f"{LogFormatter.BOX_BOTTOM_LEFT}{LogFormatter.BOX_HORIZONTAL * 76}{LogFormatter.BOX_BOTTOM_RIGHT}")


def log_table(
    logger: logging.Logger,
    headers: List[str],
    rows: List[List[str]],
    alignments: Optional[List[str]] = None,
    level: int = logging.INFO
):
    """
     ASCII 

    Args:
        logger: Logger 
        headers: 
        rows: 
        alignments:  ('left', 'center', 'right')
        level: 
    """
    table = LogFormatter.table(headers, rows, alignments)
    for line in table.split('\n'):
        logger.log(level, line)


def log_comparison(
    logger: logging.Logger,
    options: List[str],
    values: List[float],
    labels: Optional[List[str]] = None,
    highlight_index: Optional[int] = None,
    show_bar_chart: bool = True,
    level: int = logging.INFO
):
    """
    ( + )

    Args:
        logger: Logger 
        options: 
        values: ()
        labels: ()
        highlight_index: 
        show_bar_chart: 
        level: 
    """
    # 
    if labels is None:
        labels = [f"Option {i}" for i in range(len(options))]

    table_rows = []
    for i, (label, option, value) in enumerate(zip(labels, options, values)):
        marker = " " + LogFormatter.STAR if i == highlight_index else ""
        table_rows.append([label, option, f"{value:.2f}", marker])

    log_table(logger, ["Index", "Name", "Value", ""], table_rows, ['left', 'left', 'right', 'left'], level)

    # 
    if show_bar_chart:
        logger.log(level, "")
        logger.log(level, "Distance Comparison:")
        data = [(labels[i], values[i]) for i in range(len(options))]
        chart = LogFormatter.bar_chart(data, max_width=40, show_values=True, highlight_index=highlight_index)
        for line in chart.split('\n'):
            logger.log(level, line)


def log_dag_flow(
    logger: logging.Logger,
    steps: List[Dict[str, Any]],
    level: int = logging.INFO
):
    """
     DAG ()

     LogFormatter.format_dag_flow() 

    Args:
        logger: Logger 
        steps: 
        level: 
    """
    formatted = LogFormatter.format_dag_flow(steps)
    for line in formatted.split('\n'):
        logger.log(level, line)


def log_highlight_event(
    logger: logging.Logger,
    event_type: str,
    title: str,
    details: List[str],
    level: int = logging.INFO
):
    """
    (fallback, error )

    Args:
        logger: Logger 
        event_type:  ('warning', 'error', 'info', 'success')
        title: 
        details: 
        level: 
    """
    event_box = LogFormatter.highlight_event(event_type, title, details)
    for line in event_box.split('\n'):
        logger.log(level, line)


def log_llm_call(
    logger: logging.Logger,
    stage: str,
    system_prompt: str,
    user_input: str,
    response: str,
    duration: float,
    tokens: Optional[Dict[str, int]] = None,
    level: int = logging.INFO
):
    """
     LLM ()

    Args:
        logger: Logger 
        stage: ( "Route", "Plan", "Evaluate", "Generate")
        system_prompt: System Prompt 
        user_input: User Input 
        response: LLM 
        duration: ()
        tokens: Token  {"input": int, "output": int, "total": int}
        level: ( INFO)

    Example:
        log_llm_call(
            logger,
            stage="Route",
            system_prompt="...",
            user_input=": ...",
            response='{"intent": "nearby"}',
            duration=1.23,
            tokens={"input": 450, "output": 12, "total": 462}
        )
    """
    separator_full = "=" * 80
    separator_partial = "-" * 80

    # 
    logger.log(level, separator_full)
    logger.log(level, f"[{stage}] LLM Call")
    logger.log(level, separator_partial)

    # System Prompt()
    logger.log(level, f"[{stage}] System Prompt ({len(system_prompt)} chars):")
    if logger.level <= logging.DEBUG:
        # DEBUG : prompt
        logger.log(level, separator_partial)
        for line in system_prompt.split('\n'):
            logger.log(level, line)
    else:
        # INFO : 300 
        logger.log(level, separator_partial)
        if len(system_prompt) > 300:
            preview = system_prompt[:300] + f"... (truncated, total {len(system_prompt)} chars)"
            logger.log(level, preview)
        else:
            logger.log(level, system_prompt)

    # User Input
    logger.log(level, separator_partial)
    logger.log(level, f"[{stage}] User Input:")
    logger.log(level, separator_partial)
    for line in user_input.split('\n'):
        logger.log(level, line)

    # LLM Response
    logger.log(level, separator_partial)
    logger.log(level, f"[{stage}] LLM Response:")
    logger.log(level, separator_partial)
    for line in response.split('\n'):
        logger.log(level, line)

    # 
    logger.log(level, separator_partial)
    logger.log(level, f"[{stage}] Statistics:")
    logger.log(level, f"  Duration: {format_duration(duration)}")

    if tokens:
        input_tokens = tokens.get('input', 0)
        output_tokens = tokens.get('output', 0)
        total_tokens = tokens.get('total', input_tokens + output_tokens)

        # (GPT-4o-mini )
        # Input: $0.15/1M tokens, Output: $0.60/1M tokens
        cost_input = (input_tokens / 1_000_000) * 0.15
        cost_output = (output_tokens / 1_000_000) * 0.60
        cost_total = cost_input + cost_output

        logger.log(level, f"  Tokens: input={input_tokens}, output={output_tokens}, total={total_tokens}")
        logger.log(level, f"  Cost: ${cost_total:.6f} (input: ${cost_input:.6f}, output: ${cost_output:.6f})")

    # 
    logger.log(level, separator_full)
    logger.log(level, "")
