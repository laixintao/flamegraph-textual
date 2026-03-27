import logging

from flamegraph_textual.exceptions import ProfileParseException
from flamegraph_textual.parsers.pprof_parser import ProfileParser as PprofParser
from flamegraph_textual.parsers.stackcollapse_parser import StackCollapseParser

logger = logging.getLogger(__name__)


ALL_PARSERS = [PprofParser, StackCollapseParser]
PARSERS_BY_TYPE = {
    "pprof": PprofParser,
    "stackcollapse": StackCollapseParser,
    "austin": StackCollapseParser,
}


def choose_parser(content: bytes, profile_type: str | None = None):
    if profile_type is not None:
        normalized_profile_type = profile_type.strip().lower()
        try:
            return PARSERS_BY_TYPE[normalized_profile_type]
        except KeyError as exc:
            supported = ", ".join(sorted(PARSERS_BY_TYPE))
            raise ProfileParseException(
                f"Unsupported profile_type {profile_type!r}. "
                f"Supported values: {supported}"
            ) from exc

    for p in ALL_PARSERS:
        if p.validate(content):
            return p
    raise ProfileParseException("Can not match any parser")


def parse(filecontent: bytes, filename, profile_type: str | None = None):
    parser_cls = choose_parser(filecontent, profile_type=profile_type)
    logger.info("Using %s...", parser_cls)
    parser = parser_cls(filename)
    profile = parser.parse(filecontent)
    return profile
