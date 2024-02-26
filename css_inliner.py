import argparse
import logging
from dataclasses import dataclass
from itertools import chain
from typing import Any
from typing import Iterable
from typing import TypedDict

import cssutils
from bs4 import BeautifulSoup
from bs4 import ResultSet
from bs4 import Tag
from cssutils.parse import CSSParser
from cssutils.util import xml


CssSelector = str
CssSelectors = tuple[str, ...]
CssStyleDefinition = list[str]
CssInlineStyleDefinition = str
CssDict = dict[CssSelector, CssStyleDefinition]
InlineCssDict = dict[CssSelectors, CssInlineStyleDefinition]


@dataclass
class InlineCSSArgs:
    input_html: str
    output_html: str
    silent: bool


class ProcessedDeclarations(TypedDict):
    successful_declaration: CssDict
    failed_declaration: list[str]


def get_arguments() -> InlineCSSArgs:
    parser = argparse.ArgumentParser(description="")
    parser.add_argument(
        "--input-html",
        type=str,
        required=True,
        help="The path of the input html file.",
    )
    parser.add_argument(
        "--output-html",
        type=str,
        required=True,
        help="The path of the output html file.",
    )
    parser.add_argument(
        "--silent",
        action="store_true",
        help=("Surpresses all warnings."),
    )
    return InlineCSSArgs(**vars(parser.parse_args()))


def get_soup_from_html_file(file_path: str) -> BeautifulSoup:
    with open(file_path, "r") as file:
        html_content = file.read()
    soup = BeautifulSoup(html_content, "html.parser")
    return soup


def _add_closing_tag(declaration: str) -> str:
    return f"{declaration}}}".strip()


def _remove_style_tags_from_soup(style_tags: ResultSet[Any]) -> None:
    for rag in style_tags:
        rag.extract()


def format_css_content_for_inline(css_text: str) -> str:
    css_content_items: list[str] = css_text.strip().splitlines()
    formatted_css_items: list[str] = [
        f"{item.replace(';', '')};" for item in css_content_items
    ]
    joined_css_items: str = " ".join(formatted_css_items)
    return joined_css_items


def divide_declarations_from_style_tags(
    style_tags: ResultSet[Any],
) -> tuple[str, ...]:
    individual_declerations: list[tuple[str, ...]] = [
        tuple(map(_add_closing_tag, tag.string.split("}")))
        for tag in style_tags
    ]
    flattened_declarations: tuple[str, ...] = tuple(
        filter(lambda x: x.strip() != "}", chain(*individual_declerations))
    )
    return flattened_declarations


def process_css_declarations(
    parser: CSSParser, declarations: Iterable[str]
) -> ProcessedDeclarations:
    failed_declaration: list[str] = []
    css_declarations: CssDict = {}
    for declaration in declarations:
        try:
            parsed_css = parser.parseString(declaration)
        except xml.dom.SyntaxErr:
            failed_declaration.append(declaration)
            continue

        for css_dict in parsed_css:
            try:
                css_selector: str = css_dict.selectorText
                formatted_css_items: str = format_css_content_for_inline(
                    css_dict.style.cssText
                )

                css_declarations.setdefault(css_selector, [])
                css_declarations[css_selector].append(formatted_css_items)
            except AttributeError:
                continue
    return {
        "successful_declaration": css_declarations,
        "failed_declaration": failed_declaration,
    }


def inline_css_declarations(css_declarations: CssDict) -> InlineCssDict:
    result: InlineCssDict = {}
    for selector, declarations in css_declarations.items():
        split_selectors: tuple[str, ...] = tuple(
            map(str.strip, selector.split(","))
        )
        joined_declarations = " ".join(declarations)
        result[split_selectors] = joined_declarations
    return result


def apply_selectors_to_elements_as_inline_css(
    soup: BeautifulSoup, no_pseudo_selectors: Iterable[str], inline_style: str
) -> None:
    for selector in no_pseudo_selectors:
        found_styled_items: ResultSet[Tag] = soup.select(selector)
        for item in found_styled_items:
            previous_style_attr = item.get("style")
            new_style_attr: str = ""
            if not previous_style_attr:
                new_style_attr = inline_style.rstrip(";")
            elif isinstance(previous_style_attr, list):
                new_style_attr = "; ".join(
                    (*previous_style_attr, inline_style)
                ).rstrip(";")
            elif isinstance(previous_style_attr, str):
                new_style_attr = "; ".join(
                    (previous_style_attr, inline_style)
                ).rstrip(";")
            item["style"] = new_style_attr


def insert_unprocessed_declarations(
    soup: BeautifulSoup, failed_declaration: Iterable[str]
) -> None:
    leftover_style_tag = soup.new_tag("style")
    for declaration in failed_declaration:
        leftover_style_tag.append(declaration)
    if soup.head:
        soup.head.append(leftover_style_tag)


def write_soup_output(soup: BeautifulSoup, output_path: str) -> None:
    with open(output_path, "w", encoding="UTF-8") as output_file:
        output_file.write(str(soup))


def main() -> int:
    args: InlineCSSArgs = get_arguments()

    if args.silent:
        cssutils.log.setLevel(logging.CRITICAL)  # type: ignore
    else:
        cssutils.log.setLevel(logging.FATAL)  # type: ignore

    soup: BeautifulSoup = get_soup_from_html_file(args.input_html)
    parser: CSSParser = CSSParser(raiseExceptions=True)

    style_tags: ResultSet[Any] = soup.find_all("style")
    declarations: tuple[str, ...] = divide_declarations_from_style_tags(
        style_tags
    )

    processed_declarations: ProcessedDeclarations = process_css_declarations(
        parser, declarations
    )
    inlined_css_declarations: InlineCssDict = inline_css_declarations(
        processed_declarations["successful_declaration"]
    )

    pseudo_style_declarations: dict[tuple[str, ...], str] = {}
    for selectors, inline_style in inlined_css_declarations.items():
        pseudo_selectors: tuple[str, ...] = tuple(
            filter(lambda x: ":" in x, selectors)
        )
        pseudo_style_declarations.setdefault(pseudo_selectors, inline_style)

        no_pseudo_selectors: tuple[str, ...] = tuple(
            filter(lambda x: ":" not in x, selectors)
        )
        if not no_pseudo_selectors:
            continue

        apply_selectors_to_elements_as_inline_css(
            soup, no_pseudo_selectors, inline_style
        )

    _remove_style_tags_from_soup(style_tags)
    insert_unprocessed_declarations(
        soup, processed_declarations["failed_declaration"]
    )

    write_soup_output(soup, args.output_html)
    return 0
