"""
CLI administrativa segura do Job Hunter.

Provisionar administrador:
    python -m app.cli create-admin --email seu@email.com --display-name "Seu Nome"

Importar perfil privado a partir de arquivo JSON local:
    python -m app.cli import-profile-seed --email seu@email.com --file /run/local-seeds/profile-seed.local.json
"""

import argparse
import getpass
import os
import sys
import uuid
from pathlib import Path

from pydantic import ValidationError
from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.user import User
from app.schemas.profile import ProfileSeedDocumentSchema
from app.services.auth_service import create_user_account
from app.services.profile_service import get_or_create_profile, import_profile_seed_for_user


def _read_password(password_from_stdin: bool, password_env_var: str | None) -> str:
    if password_env_var:
        env_val = os.environ.get(password_env_var)
        if not env_val:
            raise ValueError(
                f"A variável de ambiente '{password_env_var}' não está definida ou está vazia."
            )
        return env_val

    if password_from_stdin:
        return sys.stdin.readline().rstrip("\r\n")

    first = getpass.getpass("Digite a senha do administrador (mínimo 8 caracteres): ")
    second = getpass.getpass("Confirme a senha do administrador: ")
    if first != second:
        raise ValueError("As senhas informadas não coincidem.")
    return first


def handle_create_admin(args: argparse.Namespace) -> int:
    try:
        password = _read_password(args.password_stdin, args.password_env)
    except ValueError as err:
        print(f"[ERRO] {err}", file=sys.stderr)
        return 1

    with SessionLocal() as db:
        try:
            user = create_user_account(
                db,
                email=args.email,
                display_name=args.display_name,
                password=password,
                is_admin=not args.regular_user,
            )
            get_or_create_profile(db, user)

            role_label = "Administrador" if user.is_admin else "Usuário"
            print(
                f"[OK] {role_label} provisionado com sucesso: id={user.id} | email={user.email}"
            )
            return 0
        except ValueError as err:
            print(f"[ERRO] {err}", file=sys.stderr)
            return 1


def handle_import_profile_seed(args: argparse.Namespace) -> int:
    seed_path = Path(args.file)
    if not seed_path.is_file():
        print(
            f"[ERRO] Arquivo de seed não encontrado: '{seed_path}'.",
            file=sys.stderr,
        )
        return 1

    try:
        raw_content = seed_path.read_text(encoding="utf-8")
        seed_doc = ProfileSeedDocumentSchema.model_validate_json(raw_content)
    except (OSError, UnicodeDecodeError) as err:
        print(f"[ERRO] Falha ao ler o arquivo de seed: {err}", file=sys.stderr)
        return 1
    except ValidationError as err:
        print(
            f"[ERRO] Estrutura JSON do seed inválida:\n{err}",
            file=sys.stderr,
        )
        return 1

    with SessionLocal() as db:
        user: User | None = None
        if args.user_id:
            try:
                parsed_id = uuid.UUID(args.user_id)
            except ValueError:
                print(
                    f"[ERRO] UUID inválido informado em --user-id: '{args.user_id}'.",
                    file=sys.stderr,
                )
                return 1
            user = db.execute(select(User).where(User.id == parsed_id)).scalar_one_or_none()
        elif args.email:
            normalized_email = args.email.strip().lower()
            user = db.execute(
                select(User).where(User.email == normalized_email)
            ).scalar_one_or_none()

        if user is None:
            print(
                "[ERRO] Usuário destino não encontrado no banco de dados.",
                file=sys.stderr,
            )
            return 1

        try:
            summary = import_profile_seed_for_user(db, user, seed_doc)
        except Exception as err:
            print(
                f"[ERRO] Falha ao importar perfil (rollback aplicado): {err}",
                file=sys.stderr,
            )
            return 1

        print(
            f"[OK] Importação concluída para user_id={user.id}: "
            f"perfil_criado={summary.profile_created}, "
            f"campos_preenchidos={summary.profile_fields_filled}, "
            f"preferencias_aplicadas={summary.preferences_applied}, "
            f"experiencias=+{summary.experiences_created}/~{summary.experiences_skipped}, "
            f"formacoes=+{summary.educations_created}/~{summary.educations_skipped}, "
            f"habilidades=+{summary.skills_created}/~{summary.skills_skipped}, "
            f"idiomas=+{summary.languages_created}/~{summary.languages_skipped}, "
            f"projetos=+{summary.projects_created}/~{summary.projects_skipped}"
        )
        return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m app.cli",
        description="Ferramenta de administração segura do Job Hunter.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    create_admin = subparsers.add_parser(
        "create-admin",
        help="Provisiona de forma segura um administrador (ou usuário) sem expor credenciais padrão.",
    )
    create_admin.add_argument(
        "--email",
        required=True,
        help="E-mail único do usuário.",
    )
    create_admin.add_argument(
        "--display-name",
        required=True,
        help="Nome de exibição do usuário.",
    )
    create_admin.add_argument(
        "--regular-user",
        action="store_true",
        help="Cria a conta como usuário comum em vez de administrador.",
    )
    create_admin.add_argument(
        "--password-stdin",
        action="store_true",
        help="Lê a senha da entrada padrão (stdin) para scripts automatizados.",
    )
    create_admin.add_argument(
        "--password-env",
        default=None,
        help="Nome de uma variável de ambiente contendo a senha a ser lida.",
    )
    create_admin.set_defaults(func=handle_create_admin)

    import_seed = subparsers.add_parser(
        "import-profile-seed",
        help="Importa dados profissionais de um arquivo JSON local privado de forma idempotente.",
    )
    target_group = import_seed.add_mutually_exclusive_group(required=True)
    target_group.add_argument(
        "--email",
        help="E-mail do usuário destino já cadastrado.",
    )
    target_group.add_argument(
        "--user-id",
        help="UUID do usuário destino já cadastrado.",
    )
    import_seed.add_argument(
        "--file",
        required=True,
        help="Caminho para o arquivo JSON local (ex: /run/local-seeds/profile-seed.local.json).",
    )
    import_seed.set_defaults(func=handle_import_profile_seed)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
