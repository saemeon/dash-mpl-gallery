"""Generate a brand package from the template.

Usage::

    python -m mpl_brandpacker.create_brand my_company
    python -m mpl_brandpacker.create_brand my_company --author "Jane Doe" --email "jane@acme.com"
    python -m mpl_brandpacker.create_brand my_company --description "Acme Corp chart styling"

Or from Python::

    from mpl_brandpacker.create_brand import create_brand
    create_brand("my_company", author="Jane Doe", description="Acme charts")
"""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path


TEMPLATE_DIR = Path(__file__).parent.parent.parent / "template"

def create_brand(
    name: str,
    output: str | Path | None = None,
    author: str = "Your Name",
    email: str = "you@example.com",
    description: str = "",
) -> Path:
    """Generate a brand package from the built-in template.

    Parameters
    ----------
    name :
        Package name (e.g. ``"my_company"``). Used as the Python module name.
    output :
        Output directory. Defaults to ``./<name>/``.
    author :
        Author name for pyproject.toml and LICENSE.
    email :
        Author email for pyproject.toml.
    description :
        One-line package description.
    license :
        License type (used in pyproject.toml).

    Returns
    -------
    Path
        The output directory.
    """
    name = name.strip().replace("-", "_").replace(" ", "_").lower()
    name_hyphen = name.replace("_", "-")
    output_dir = Path(output or f"./{name}")

    if output_dir.exists():
        raise FileExistsError(f"{output_dir} already exists")

    if not TEMPLATE_DIR.exists():
        raise FileNotFoundError(
            f"Template not found at {TEMPLATE_DIR}. "
            "Make sure mpl-brandpacker is installed from source."
        )

    if not description:
        description = f"{name_hyphen} — branded matplotlib package"

    # Copy template
    shutil.copytree(TEMPLATE_DIR, output_dir)

    # Rename src/my_brand → src/<name>
    old_pkg = output_dir / "src" / "my_brand"
    new_pkg = output_dir / "src" / name
    if old_pkg.exists():
        old_pkg.rename(new_pkg)

    # Replace placeholders in all text files
    replacements = {
        "my_brand": name,
        "my-brand": name_hyphen,
        "Your Name / Your Company": author,
        "Your Name": author,
        "you@example.com": email,
        "Branded matplotlib package — replace with your brand description": description,
    }

    for path in output_dir.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix not in (".py", ".toml", ".md", ".mplstyle", ""):
            # Also handle LICENSE (no extension)
            if path.name != "LICENSE":
                continue
        text = path.read_text()
        for old, new in replacements.items():
            text = text.replace(old, new)
        path.write_text(text)

    return output_dir


def main():
    parser = argparse.ArgumentParser(
        description="Generate a brand package from template",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Example:\n  python -m mpl_brandpacker.create_brand acme_corp --author 'Jane Doe'",
    )
    parser.add_argument("name", help="Package name (e.g. acme_corp)")
    parser.add_argument("--output", "-o", help="Output directory (default: ./<name>/)")
    parser.add_argument("--author", "-a", default="Your Name", help="Author name")
    parser.add_argument("--email", "-e", default="you@example.com", help="Author email")
    parser.add_argument("--description", "-d", default="", help="Package description")
    args = parser.parse_args()

    name = args.name.strip().replace("-", "_").replace(" ", "_").lower()
    output = create_brand(
        name, args.output,
        author=args.author, email=args.email, description=args.description,
    )
    print(f"Created brand package: {output}/")
    print(f"  cd {output}")
    print(f"  pip install -e .")
    print(f"  python -c 'import {name}.pyplot as plt; plt.subplots(); plt.show()'")


if __name__ == "__main__":
    main()
