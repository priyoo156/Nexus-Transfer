import sqlite3
import unittest
from pathlib import Path

from app import DATABASE, app, validate_token


class TokenAndQrValidationTests(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()
        self.conn = sqlite3.connect(DATABASE)
        self.conn.execute(
            "INSERT OR IGNORE INTO orders (order_id, filename, original_filename, stored_filename, mode, copies, total_pages, total, status, uploaded_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ('NEXUS-ABC12345', 'test.pdf', 'test.pdf', 'test.pdf', 'bw', 1, 1, 1.0, 'Pending', '2026-07-03T00:00:00')
        )
        self.conn.commit()

    def tearDown(self):
        self.conn.execute("DELETE FROM orders WHERE order_id = ?", ('NEXUS-ABC12345',))
        self.conn.commit()
        self.conn.close()

    def test_backend_accepts_8_character_tokens_and_rejects_short_tokens(self):
        self.assertEqual(validate_token('NEXUS-ABC12345'), 'NEXUS-ABC12345')
        self.assertIsNone(validate_token('NEXUS-1234'))
        self.assertIsNone(validate_token('invalid-token'))

    def test_qr_endpoint_requires_valid_token(self):
        response = self.client.post('/qr-code', json={'token': 'NEXUS-ABC12345'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, 'image/png')

        bad_response = self.client.post('/qr-code', json={'token': 'NEXUS-1234'})
        self.assertEqual(bad_response.status_code, 400)

    def test_frontend_uses_8_character_token_validation(self):
        template = Path('templates/nexus.html').read_text(encoding='utf-8')
        self.assertIn("/^NEXUS-[A-Z0-9]{8}$/", template)


if __name__ == '__main__':
    unittest.main()
