"""Unit tests for the Zenity UI abstraction layer."""

import unittest
from unittest.mock import patch, MagicMock

from nosteam2steam import ui


class TestUI(unittest.TestCase):
    @patch("subprocess.run")
    def test_show_info(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0)
        ui.show_info(title="Info Title", text="Info Text", timeout=3, width=400)

        mock_run.assert_called_once()
        args = mock_run.call_args[0][0]
        self.assertEqual(args[0], "zenity")
        self.assertEqual(args[1], "--info")
        self.assertIn("--title=Info Title", args)
        self.assertIn("--text=Info Text", args)
        self.assertIn("--timeout=3", args)
        self.assertIn("--width=400", args)

    @patch("subprocess.run")
    def test_show_error(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0)
        ui.show_error(title="Err Title", text="Err Text")

        mock_run.assert_called_once()
        args = mock_run.call_args[0][0]
        self.assertEqual(args[1], "--error")
        self.assertIn("--title=Err Title", args)
        self.assertIn("--text=Err Text", args)

    @patch("subprocess.run")
    def test_ask_question(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0)
        result = ui.ask_question(title="Q Title", text="Q Text", ok_label="Accept", cancel_label="Reject")

        self.assertTrue(result)
        args = mock_run.call_args[0][0]
        self.assertEqual(args[1], "--question")
        self.assertIn("--ok-label=Accept", args)
        self.assertIn("--cancel-label=Reject", args)

    @patch("subprocess.run")
    def test_show_menu(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="2\n")
        items = [("1", "Option One"), ("2", "Option Two")]
        selected = ui.show_menu(title="Menu", text="Choose:", menu_items=items)

        self.assertEqual(selected, "2")
        args = mock_run.call_args[0][0]
        self.assertEqual(args[1], "--list")
        self.assertIn("--column=Option", args)
        self.assertIn("--column=Description", args)
        self.assertIn("Option One", args)
        self.assertIn("Option Two", args)

    @patch("subprocess.run")
    def test_select_path(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="/home/deck/Games\n")
        path = ui.select_path(title="Select Folder", directory=True)

        self.assertEqual(path, "/home/deck/Games")
        args = mock_run.call_args[0][0]
        self.assertEqual(args[1], "--file-selection")
        self.assertIn("--directory", args)

    @patch("subprocess.run")
    def test_show_checklist(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="FolderA\nFolderB\n")
        items = [("FolderA", True), ("FolderB", False)]
        selected = ui.show_checklist(title="Check", text="Select:", items=items)

        self.assertEqual(selected, ["FolderA", "FolderB"])
        args = mock_run.call_args[0][0]
        self.assertIn("--checklist", args)
        self.assertIn("--multiple", args)

    @patch("subprocess.run")
    def test_show_radiolist(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="Opt1\n")
        items = [("Opt1", "Option 1", True), ("Opt2", "Option 2", False)]
        selected = ui.show_radiolist(title="Radio", text="Choose:", items=items)

        self.assertEqual(selected, "Opt1")
        args = mock_run.call_args[0][0]
        self.assertIn("--radiolist", args)

    @patch("nosteam2steam.ui.get_dialog_backend", return_value="kdialog")
    @patch("subprocess.run")
    def test_kdialog_fallback_dialogs(self, mock_run, mock_backend):
        mock_run.return_value = MagicMock(returncode=0, stdout="test_out\n")

        ui.show_info(title="KInfo", text="Text")
        args = mock_run.call_args[0][0]
        self.assertEqual(args[0], "kdialog")
        self.assertIn("--msgbox=Text", args)

        ui.show_error(title="KErr", text="ErrText")
        args = mock_run.call_args[0][0]
        self.assertEqual(args[0], "kdialog")
        self.assertIn("--error=ErrText", args)

        ui.ask_question(title="KQ", text="QText")
        args = mock_run.call_args[0][0]
        self.assertEqual(args[0], "kdialog")
        self.assertIn("--yesno=QText", args)

    def test_cli_argument_parsing(self):
        from nosteam2steam.app import parse_arguments

        # Default empty flags
        args = parse_arguments([])
        self.assertFalse(args.sync)
        self.assertFalse(args.add_games)
        self.assertFalse(args.sync_saves)
        self.assertFalse(args.clean_config)
        self.assertFalse(args.quiet)

        # Flag activation
        args = parse_arguments(["--sync", "-q"])
        self.assertTrue(args.sync)
        self.assertTrue(args.quiet)

        args = parse_arguments(["--add-games"])
        self.assertTrue(args.add_games)

        args = parse_arguments(["--sync-saves"])
        self.assertTrue(args.sync_saves)

        args = parse_arguments(["--clean-config"])
        self.assertTrue(args.clean_config)

    @patch("subprocess.Popen")
    @patch("nosteam2steam.ui.get_dialog_backend", return_value="zenity")
    def test_progress_dialog_zenity(self, mock_backend, mock_popen):
        mock_proc = MagicMock()
        mock_proc.poll.return_value = None
        mock_popen.return_value = mock_proc

        with ui.progress_dialog(title="Test Title", text="Initial Text") as progress:
            self.assertIsNotNone(progress)
            progress.update("Step 2", percentage=50)

        mock_popen.assert_called_once()
        args = mock_popen.call_args[0][0]
        self.assertEqual(args[0], "zenity")
        self.assertIn("--progress", args)
        self.assertIn("--title=Test Title", args)
        mock_proc.stdin.write.assert_any_call("50\n")
        mock_proc.stdin.write.assert_any_call("# Step 2\n")
        mock_proc.terminate.assert_called_once()

    @patch("subprocess.Popen")
    @patch("nosteam2steam.ui.get_dialog_backend", return_value="kdialog")
    def test_progress_dialog_kdialog(self, mock_backend, mock_popen):
        mock_proc = MagicMock()
        mock_popen.return_value = mock_proc

        with ui.progress_dialog(title="KDialog Title", text="Working...") as progress:
            progress.update("Still working...")

        mock_popen.assert_called_once()
        args = mock_popen.call_args[0][0]
        self.assertEqual(args[0], "kdialog")
        mock_proc.terminate.assert_called_once()

    @patch("nosteam2steam.ui.get_dialog_backend", return_value="none")
    def test_progress_dialog_headless(self, mock_backend):
        # Should gracefully no-op without launching any subprocess
        with ui.progress_dialog(title="Headless", text="Running in background...") as progress:
            progress.update("Silent update")
        self.assertIsNone(progress.process)


if __name__ == "__main__":
    unittest.main()
