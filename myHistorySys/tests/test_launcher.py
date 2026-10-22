"""Opening the API must not create or start a PostgreSQL instance."""
import unittest
from unittest.mock import MagicMock,patch
import launch_service
import init_local


class LauncherTests(unittest.TestCase):
    @patch('launch_service.subprocess.run')
    @patch('launch_service.connect')
    def test_unavailable_database_does_not_launch_postgres(self,connect,run):
        connect.side_effect=OSError('synthetic connection failure')
        with self.assertRaisesRegex(RuntimeError,'no database instance was started'):
            launch_service.ensure_database()
        run.assert_not_called()

    @patch('launch_service.subprocess.run')
    @patch('launch_service.connect')
    def test_preflight_does_not_run_ddl(self,connect,run):
        connection=MagicMock()
        connect.return_value.__enter__.return_value=connection
        connection.execute.return_value.fetchone.return_value={'ready':True}
        launch_service.ensure_database()
        run.assert_not_called()
        self.assertEqual(connection.execute.call_count,1)
        self.assertTrue(connection.execute.call_args.args[0].startswith('SELECT '))

    @patch('launch_service.connect')
    def test_missing_schema_is_not_created(self,connect):
        connect.return_value.__enter__.return_value.execute.return_value.fetchone.return_value={'ready':False}
        with self.assertRaisesRegex(RuntimeError,'schema missing'):
            launch_service.ensure_database()

    @patch('sys.argv',['launch_service.py','--no-browser'])
    @patch('launch_service.subprocess.Popen')
    @patch('launch_service.subprocess.run')
    @patch('launch_service.connect',side_effect=OSError('synthetic connection failure'))
    def test_failed_preflight_does_not_start_any_process(self,connect,run,popen):
        with self.assertRaises(RuntimeError):
            launch_service.main()
        run.assert_not_called();popen.assert_not_called()

    @patch('sys.argv',['init_local.py'])
    @patch('init_local.subprocess.run')
    def test_private_cluster_requires_explicit_flag(self,run):
        with patch('sys.stderr'),self.assertRaises(SystemExit) as result:
            init_local.main()
        self.assertEqual(result.exception.code,2)
        run.assert_not_called()

if __name__=='__main__':unittest.main()
