import unittest

from config_manager import ConfigurationManager, create_enhanced_argument_parser


class TargetModeCliTests(unittest.TestCase):
	def setUp(self):
		self.parser = create_enhanced_argument_parser()

	def test_target_mode_alias_selects_modem(self):
		args = self.parser.parse_args(['N0CALL', '--target-mode', 'modem'])

		self.assertEqual(args.target_type, 'modem')

	def test_target_type_selects_modem(self):
		args = self.parser.parse_args(['N0CALL', '--target-type', 'modem'])

		self.assertEqual(args.target_type, 'modem')

	def test_cli_target_mode_updates_both_config_views(self):
		args = self.parser.parse_args([
			'N0CALL',
			'--target-mode', 'modem',
			'--keepalive-interval', '3.5',
		])
		manager = ConfigurationManager()

		config = manager.merge_cli_args(args)

		self.assertEqual(config.protocol.target_type, 'modem')
		self.assertEqual(config.network.target_type, 'modem')
		self.assertEqual(config.protocol.keepalive_interval, 3.5)
		self.assertEqual(config.network.keepalive_interval, 3.5)
		self.assertEqual(config.to_dict()['network']['target_type'], 'modem')


if __name__ == '__main__':
	unittest.main()
