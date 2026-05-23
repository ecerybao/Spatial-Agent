"""
 - 

:
- ASCII 
- 
- 
- 
- 
"""

from typing import List, Dict, Any, Optional, Union
import textwrap


class LogFormatter:
    """"""

    # (Box-drawing characters)
    BOX_HORIZONTAL = "-"
    BOX_VERTICAL = "|"
    BOX_TOP_LEFT = "+"
    BOX_TOP_RIGHT = "+"
    BOX_BOTTOM_LEFT = "+"
    BOX_BOTTOM_RIGHT = "+"
    BOX_CROSS = "+"
    BOX_T_DOWN = "+"
    BOX_T_UP = "+"
    BOX_T_RIGHT = "+"
    BOX_T_LEFT = "+"

    # ( logging_utils.SYMBOLS )
    # : logging_utils.py  SYMBOLS 
    # ,
    CHECKMARK = "OK"  #  SYMBOLS['success']
    CROSS = "X"  #  SYMBOLS['error']
    STAR = ""  #  SYMBOLS['star']
    WARNING = "WARNING"  #  SYMBOLS['warning']
    ERROR = "ERROR"  #  SYMBOLS['cross']
    SUCCESS = "OK"  #  SYMBOLS['check']
    INFO = "INFO"  #  SYMBOLS['info']
    LOCATION = ""  #  SYMBOLS['location']
    TIME = "TIME"  #  SYMBOLS['time']
    ARROW_RIGHT = "->"  #  SYMBOLS['arrow_right']
    ARROW_DOWN = "v"  #  SYMBOLS['arrow_down']

    @staticmethod
    def phase_header(title: str, width: int = 78, emoji: str = "") -> str:
        """
        

        Args:
            title: 
            width: 
            emoji:  emoji 

        Returns:
            
        """
        full_title = f"{emoji} {title}" if emoji else title
        padding = width - len(full_title) - 4  # 

        top = f"{LogFormatter.BOX_TOP_LEFT}{LogFormatter.BOX_HORIZONTAL * (width - 2)}{LogFormatter.BOX_TOP_RIGHT}"
        middle = f"{LogFormatter.BOX_VERTICAL} {full_title}{' ' * padding} {LogFormatter.BOX_VERTICAL}"
        bottom = f"{LogFormatter.BOX_BOTTOM_LEFT}{LogFormatter.BOX_HORIZONTAL * (width - 2)}{LogFormatter.BOX_BOTTOM_RIGHT}"

        return f"{top}\n{middle}\n{bottom}"

    @staticmethod
    def section_header(title: str, width: int = 78) -> str:
        """
        

        Args:
            title: 
            width: 

        Returns:
            
        """
        top = f"{LogFormatter.BOX_TOP_LEFT}{LogFormatter.BOX_HORIZONTAL * (width - 2)}{LogFormatter.BOX_TOP_RIGHT}"
        padding = width - len(title) - 4
        middle = f"{LogFormatter.BOX_VERTICAL} {title}{' ' * padding} {LogFormatter.BOX_VERTICAL}"
        separator = f"{LogFormatter.BOX_T_RIGHT}{LogFormatter.BOX_HORIZONTAL * (width - 2)}{LogFormatter.BOX_T_LEFT}"

        return f"{top}\n{middle}\n{separator}"

    @staticmethod
    def table(
        headers: List[str],
        rows: List[List[str]],
        alignments: Optional[List[str]] = None
    ) -> str:
        """
         ASCII 

        Args:
            headers: 
            rows: 
            alignments:  ('left', 'center', 'right')

        Returns:
            
        """
        if not headers or not rows:
            return ""

        # 
        if alignments is None:
            alignments = ['left'] * len(headers)

        # 
        col_widths = []
        for i, header in enumerate(headers):
            max_width = len(header)
            for row in rows:
                if i < len(row):
                    max_width = max(max_width, len(str(row[i])))
            col_widths.append(max_width)

        # 
        def make_separator(left, cross, right):
            parts = [left]
            for i, width in enumerate(col_widths):
                parts.append(LogFormatter.BOX_HORIZONTAL * (width + 2))
                if i < len(col_widths) - 1:
                    parts.append(cross)
            parts.append(right)
            return ''.join(parts)

        # 
        def make_row(cells, widths, aligns):
            parts = [LogFormatter.BOX_VERTICAL]
            for i, (cell, width, align) in enumerate(zip(cells, widths, aligns)):
                cell_str = str(cell)
                if align == 'center':
                    formatted = cell_str.center(width)
                elif align == 'right':
                    formatted = cell_str.rjust(width)
                else:  # left
                    formatted = cell_str.ljust(width)
                parts.append(f" {formatted} ")
                parts.append(LogFormatter.BOX_VERTICAL)
            return ''.join(parts)

        # 
        lines = []
        lines.append(make_separator(
            LogFormatter.BOX_TOP_LEFT,
            LogFormatter.BOX_T_DOWN,
            LogFormatter.BOX_TOP_RIGHT
        ))
        lines.append(make_row(headers, col_widths, ['center'] * len(headers)))
        lines.append(make_separator(
            LogFormatter.BOX_T_RIGHT,
            LogFormatter.BOX_CROSS,
            LogFormatter.BOX_T_LEFT
        ))
        for row in rows:
            # 
            padded_row = row + [''] * (len(headers) - len(row))
            lines.append(make_row(padded_row, col_widths, alignments))
        lines.append(make_separator(
            LogFormatter.BOX_BOTTOM_LEFT,
            LogFormatter.BOX_T_UP,
            LogFormatter.BOX_BOTTOM_RIGHT
        ))

        return '\n'.join(lines)

    @staticmethod
    def bar_chart(
        data: List[tuple],
        max_width: int = 40,
        show_values: bool = True,
        highlight_index: Optional[int] = None
    ) -> str:
        """
        

        Args:
            data: [(label, value), ...] 
            max_width: ()
            show_values: 
            highlight_index: ()

        Returns:
            
        """
        if not data:
            return ""

        # 
        max_value = max(value for _, value in data)
        if max_value == 0:
            max_value = 1  # 

        lines = []
        for i, (label, value) in enumerate(data):
            # 
            bar_length = int((value / max_value) * max_width)
            filled = "#" * bar_length
            empty = "." * (max_width - bar_length)
            bar = filled + empty

            # 
            marker = f" {LogFormatter.STAR}" if i == highlight_index else ""

            # 
            value_str = f" {value:.2f}" if isinstance(value, float) else f" {value}"
            value_part = value_str if show_values else ""

            lines.append(f"  {label}: {bar}{value_part}{marker}")

        return '\n'.join(lines)

    @staticmethod
    def tree(
        root: str,
        children: List[Union[str, tuple]],
        indent: str = "  "
    ) -> str:
        """
        

        Args:
            root: 
            children: , (text, sub_children) 
            indent: 

        Returns:
            
        """
        lines = [root]

        for i, child in enumerate(children):
            is_last = (i == len(children) - 1)
            prefix = "+-" if is_last else "+-"
            connector = "  " if is_last else "| "

            if isinstance(child, tuple):
                text, sub_children = child
                lines.append(f"{prefix} {text}")
                for sub_child in sub_children:
                    lines.append(f"{connector}{indent}{sub_child}")
            else:
                lines.append(f"{prefix} {child}")

        return '\n'.join(lines)

    @staticmethod
    def highlight_event(
        event_type: str,
        title: str,
        details: List[str],
        width: int = 78
    ) -> str:
        """
        ( fallback, error)

        Args:
            event_type:  ('warning', 'error', 'info', 'success')
            title: 
            details: 
            width: 

        Returns:
            
        """
        # 
        icon_map = {
            'warning': LogFormatter.WARNING,
            'error': LogFormatter.ERROR,
            'info': LogFormatter.INFO,
            'success': LogFormatter.SUCCESS
        }
        icon = icon_map.get(event_type, LogFormatter.INFO)

        lines = []
        lines.append(f"{icon}  {title}")
        for detail in details:
            lines.append(f"   {LogFormatter.ARROW_RIGHT} {detail}")

        return '\n'.join(lines)

    @staticmethod
    def format_location(
        name: str,
        lat: float,
        lng: float,
        distance: Optional[float] = None
    ) -> str:
        """
         Location 

        Args:
            name: 
            lat: 
            lng: 
            distance: (km)

        Returns:
            
        """
        coords = f"{lat:.2f} degrees N, {lng:.2f} degrees E"
        if distance is not None:
            return f"{LogFormatter.LOCATION} {name} | {coords} | {distance:.2f}km"
        else:
            return f"{LogFormatter.LOCATION} {name} | {coords}"

    @staticmethod
    def format_dag_flow(steps: List[Dict[str, Any]]) -> str:
        """
         DAG  ASCII 

        Args:
            steps: 

        Returns:
             DAG 
        """
        if not steps:
            return ""

        lines = ["DAG Flow:"]
        lines.append("")

        # 
        for i, step in enumerate(steps):
            operator = step.get('operator', '?')
            before = step.get('before', [])
            after = step.get('after', [])
            desc = step.get('description', '')

            # :before -> [operator] -> after
            before_str = ', '.join(before) if before else '?'
            after_str = ', '.join(after) if after else '?'

            lines.append(f"  Step {i+1}: {before_str} {LogFormatter.ARROW_RIGHT} [{operator}] {LogFormatter.ARROW_RIGHT} {after_str}")
            if desc:
                lines.append(f"         {desc}")

        return '\n'.join(lines)

    @staticmethod
    def wrap_text(text: str, width: int = 70, indent: str = "") -> str:
        """
        

        Args:
            text: 
            width: 
            indent: 

        Returns:
            
        """
        wrapped = textwrap.fill(text, width=width, initial_indent=indent, subsequent_indent=indent)
        return wrapped
