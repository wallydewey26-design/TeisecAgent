import secrets
import string
from colorama import Fore, Style

ROLES = ['owner', 'admin', 'developer']

# Role permissions
ROLE_PERMISSIONS = {
    'owner': ['view', 'prompt', 'clear_session', 'view_session', 'manage_users'],
    'admin': ['view', 'prompt', 'clear_session', 'view_session'],
    'developer': ['view', 'prompt', 'view_session'],
}

_passkeys = {}


def _generate_passkey(length=16):
    alphabet = string.ascii_letters + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(length))


def generate_credentials():
    """Generate a random passkey for each role and print them to the console."""
    global _passkeys
    _passkeys = {role: _generate_passkey() for role in ROLES}
    print('\n' + '=' * 60)
    print(Fore.CYAN + '  Teisec Agent — Auto-Generated Login Credentials' + Style.RESET_ALL)
    print('=' * 60)
    for role in ROLES:
        color = Fore.RED if role == 'owner' else (Fore.YELLOW if role == 'admin' else Fore.GREEN)
        print(f"  {color}{role.upper():10s}{Style.RESET_ALL}  passkey: {Fore.WHITE}{_passkeys[role]}{Style.RESET_ALL}")
    print('=' * 60 + '\n')
    return _passkeys


def validate_passkey(passkey):
    """Return the role for the given passkey, or None if invalid."""
    for role, key in _passkeys.items():
        if secrets.compare_digest(key, passkey):
            return role
    return None


def get_permissions(role):
    """Return the list of permissions for a given role."""
    return ROLE_PERMISSIONS.get(role, [])
