"""
Zentrale Fehlerformatierung für Config-Validierung
"""
from pydantic_core import ValidationError

def format_validation_error(error: Exception) -> str:
    """Formatiert Pydantic ValidationError kompakt und leserlich"""
    try:
        if isinstance(error, ValidationError):
            errors = []
            for err in error.errors():
                field = '.'.join(str(loc) for loc in err['loc'])
                msg = err['msg']
                if 'greater than 0' in msg.lower():
                    msg = "muss > 0 sein"
                elif 'less than' in msg.lower():
                    msg = msg.replace('Input should be less than', 'muss <')
                elif 'greater than' in msg.lower():
                    msg = msg.replace('Input should be greater than', 'muss >')
                errors.append(f"  • {field}: {msg}" if field else f"  • {msg}")
            return '\n'.join(errors)
    except ImportError:
        pass

    error_str = str(error)
    lines = error_str.split('\n')
    filtered = [
        line for line in lines
        if not line.strip().startswith('For further information')
        and not line.strip().startswith('https://errors.pydantic')
    ]
    return '\n'.join(filtered).strip()
