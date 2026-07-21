import importlib
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from djsonapi.api import DjsonApi
from djsonapi.generator import generate, generate_typescript


class Command(BaseCommand):
    help = (
        "Generate a typed async client SDK from a DjsonApi instance, "
        "e.g. `manage.py generate_jsonapi_client articles.views::api "
        "--output ~/articles_sdk`"
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "target",
            help="Import path of the DjsonApi instance, e.g. 'articles.views::api'",
        )
        parser.add_argument(
            "--output",
            required=True,
            help="Output directory for the generated SDK package",
        )
        parser.add_argument(
            "--language",
            default="python",
            choices=["python", "typescript"],
            help="Target language (default: python)",
        )

    def handle(self, target: str, output: str, **options):
        module_name, _, attr = target.partition("::")
        attr = attr or "api"
        try:
            module = importlib.import_module(module_name)
        except ImportError as e:
            raise CommandError(f"Could not import '{module_name}': {e}") from e
        try:
            api = getattr(module, attr)
        except AttributeError as e:
            raise CommandError(f"'{module_name}' has no attribute '{attr}'") from e
        if not isinstance(api, DjsonApi):
            raise CommandError(f"'{target}' is not a DjsonApi instance")

        language = options.get("language", "python")
        if language == "python":
            output_dir = generate(api, Path(output).expanduser())
        elif language == "typescript":
            output_dir = generate_typescript(api, Path(output).expanduser())

        self.stdout.write(self.style.SUCCESS(f"Generated {language} SDK in {output_dir}"))
