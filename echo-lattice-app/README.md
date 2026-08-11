# Echo Lattice App

## Overview
The Echo Lattice App is a unique web application designed to provide users with an interactive platform for exploring and visualizing data in a lattice structure. This application leverages Flask for the backend and offers a clean, user-friendly interface.

## Features
- Interactive data visualization in a lattice format.
- User-friendly interface with responsive design.
- Modular architecture for easy maintenance and scalability.

## Installation (local, Windows)

1. Open PowerShell and navigate to the project directory:
   ```powershell
   cd C:\path\to\echo-lattice-app
   ```

2. Create and activate a virtual environment (recommended):
   ```powershell
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```

3. Install the required dependencies (a pinned `requirements.txt` is included):
   ```powershell
   python -m pip install --upgrade pip
   python -m pip install -r requirements.txt
   ```

4. Copy the example environment file and provide a secure SECRET_KEY:
   ```powershell
   copy .env.example .env
   # Edit .env and set SECRET_KEY to a strong, unique value
   ```

## Usage (development)

1. Start the development server (uses settings from `.env` when present):
   ```powershell
   # from project root (echo-lattice-app)
   .\.venv\Scripts\python -m app.main
   ```

2. Open your browser at `http://127.0.0.1:5000`.

## Security notes (local -> production)

- The app includes safer defaults for sessions (httpOnly, SameSite). For production use HTTPS and set `FLASK_ENV=production` and `USE_HTTPS=1` in your environment.
- Do not store secrets (e.g., real API keys) in the repository. Use environment variables or a secrets manager.
- For production on Windows, prefer a WSGI server like Waitress; on Linux use Gunicorn or uWSGI behind a reverse proxy (Nginx) with TLS.

## Testing

Run unit tests with:
```powershell
.\.venv\Scripts\python -m unittest discover -v tests
```

## Notes

- `requirements.txt` has been updated to match the environment used here (Flask/Werkzeug compatible with your Python 3.14 runtime). If you reproduce the setup on another machine, recreate the venv and install from `requirements.txt`.

## Testing

To run the tests, use the following command:
```
pytest tests/test_main.py
```

## Contributing

Contributions are welcome! Please open an issue or submit a pull request for any enhancements or bug fixes.

## License

This project is licensed under the MIT License. See the LICENSE file for details.
