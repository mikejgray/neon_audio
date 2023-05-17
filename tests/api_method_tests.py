# NEON AI (TM) SOFTWARE, Software Development Kit & Application Framework
# All trademark and other rights reserved by their respective owners
# Copyright 2008-2022 Neongecko.com Inc.
# Contributors: Daniel McKnight, Guy Daniels, Elon Gasper, Richard Leeds,
# Regina Bloomstine, Casimiro Ferreira, Andrii Pernatii, Kirill Hrymailo
# BSD-3 License
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
# 1. Redistributions of source code must retain the above copyright notice,
#    this list of conditions and the following disclaimer.
# 2. Redistributions in binary form must reproduce the above copyright notice,
#    this list of conditions and the following disclaimer in the documentation
#    and/or other materials provided with the distribution.
# 3. Neither the name of the copyright holder nor the names of its
#    contributors may be used to endorse or promote products derived from this
#    software without specific prior written permission.
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO,
# THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR
# PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR
# CONTRIBUTORS  BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL,
# EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO,
# PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA,
# OR PROFITS;  OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF
# LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING
# NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS
# SOFTWARE,  EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

import os
import sys
import unittest

from threading import Event
from time import time
from mock.mock import Mock
from ovos_bus_client import Message
from ovos_utils.messagebus import FakeBus
from neon_utils.configuration_utils import init_config_dir
from ovos_config.config import Configuration
from neon_utils.message_utils import dig_for_message

sys.path.append(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
from neon_audio.service import NeonPlaybackService
from neon_audio.utils import use_neon_audio


class TestAPIMethods(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        test_config_dir = os.path.join(os.path.dirname(__file__), "config")
        os.makedirs(test_config_dir, exist_ok=True)
        os.environ["XDG_CONFIG_HOME"] = test_config_dir
        use_neon_audio(init_config_dir)()

        test_config = Configuration()
        test_config["tts"]["module"] = "neon-tts-plugin-larynx-server"
        test_config["tts"]["neon-tts-plugin-larynx-server"] = \
            {"host": os.environ.get("TTS_URL") or "https://larynx.2022.us/"}
        assert test_config["tts"]["module"] == "neon-tts-plugin-larynx-server"

        # cls.messagebus = NeonBusService(debug=True, daemonic=True)
        # cls.messagebus.start()
        cls.bus = FakeBus()
        cls.bus.connected_event = Event()
        cls.bus.connected_event.set()
        cls.audio_service = NeonPlaybackService(audio_config=test_config,
                                                daemonic=True, bus=cls.bus)
        cls.audio_service.start()
        # cls.bus = MessageBusClient()
        # cls.bus.run_in_thread()
        # if not cls.bus.connected_event.wait(30):
        #     raise TimeoutError("Bus not connected after 60 seconds")
        alive = False
        timeout = time() + 120
        while not alive and time() < timeout:
            message = cls.bus.wait_for_response(Message("mycroft.audio.is_ready"))
            if message:
                alive = message.data.get("status")
        if not alive:
            raise TimeoutError("Speech module not ready after 120 seconds")

    @classmethod
    def tearDownClass(cls) -> None:
        super(TestAPIMethods, cls).tearDownClass()
        # try:
        #     cls.messagebus.shutdown()
        # except Exception as e:
        #     print(e)
        try:
            cls.audio_service.shutdown()
        except Exception as e:
            print(e)

    def test_get_tts_no_sentence(self):
        context = {"client": "tester",
                   "ident": "123",
                   "user": "TestRunner"}
        tts_resp = self.bus.wait_for_response(Message("neon.get_tts", {}, context), context["ident"])
        self.assertEqual(tts_resp.context, context)
        self.assertIsInstance(tts_resp.data.get("error"), str)
        self.assertEqual(tts_resp.data["error"], "No text provided.")

    def test_get_tts_invalid_type(self):
        context = {"client": "tester",
                   "ident": "1234",
                   "user": "TestRunner"}
        tts_resp = self.bus.wait_for_response(Message("neon.get_tts", {"text": 123}, context),
                                              context["ident"], timeout=60)
        self.assertEqual(tts_resp.context, context)
        self.assertTrue(tts_resp.data.get("error").startswith("text is not a str:"))

    def test_get_tts_valid_default(self):
        text = "This is a test"
        context = {"client": "tester",
                   "ident": str(time()),
                   "user": "TestRunner"}
        tts_resp = self.bus.wait_for_response(Message("neon.get_tts",
                                                      {"text": text}, context),
                                              context["ident"], timeout=60)
        self.assertEqual(tts_resp.context, context)
        responses = tts_resp.data
        self.assertIsInstance(responses, dict)
        print(responses)
        self.assertEqual(len(responses), 1)
        resp = list(responses.values())[0]
        self.assertIsInstance(resp, dict)
        self.assertEqual(resp.get("sentence"), text)

    # TODO: Test with multiple languages
    def test_get_tts_valid_speaker(self):
        pass

    def test_handle_speak(self):
        self.audio_service._playback_timeout = 1  # Override playback timeout
        real_method = self.audio_service.execute_tts
        mock_tts = Mock()
        self.audio_service.execute_tts = mock_tts

        # TODO: this destination handling should be deprecated
        # 'audio' not in destination
        message_invalid_destination = Message("speak",
                                              {"utterance": "test"},
                                              {"ident": "test",
                                               "destination": ['invalid']})
        self.audio_service.handle_speak(message_invalid_destination)
        mock_tts.assert_called_with("test", "test", False)

        # 'audio' in destination
        message_valid_destination = Message("speak",
                                            {"utterance": "test1"},
                                            {"ident": "test2",
                                             "destination": ['invalid',
                                                             'audio']})
        self.audio_service.handle_speak(message_valid_destination)
        mock_tts.assert_called_with("test1", "test2", False)

        # str 'audio' destination
        message_valid_destination = Message("speak",
                                            {"utterance": "test5"},
                                            {"ident": "test6",
                                             "destination": 'audio'})
        self.audio_service.handle_speak(message_valid_destination)
        mock_tts.assert_called_with("test5", "test6", False)

        # TODO: this destination handling should be deprecated
        # no destination context
        message_no_destination = Message("speak",
                                         {"utterance": "test3"},
                                         {"ident": "test4"})
        self.audio_service.handle_speak(message_no_destination)
        mock_tts.assert_called_with("test3", "test4", False)

        # Setup bus API handling
        self.audio_service._playback_timeout = 60
        msg: Message = None

        def handle_tts(*args, **kwargs):
            nonlocal msg
            msg = dig_for_message()
            ident = msg.data.get('speak_ident') or msg.data.get('ident')
            if ident:
                self.bus.emit(Message(ident))

        mock_tts.side_effect = handle_tts

        # Test No ident handling
        message_no_ident = Message("speak",
                                   {"utterance": "No Ident"},
                                   {"destination": ["audio"]})
        start_time = time()
        self.audio_service.handle_speak(message_no_ident)
        self.assertAlmostEqual(time(), start_time, 0)
        self.assertEqual(msg, message_no_ident)

        # Test `ident`
        ident = time()
        message_with_ident = Message("speak",
                                     {"utterance": "with ident",
                                      "ident": ident},
                                     {"destination": ["audio"]})
        on_ident = Mock()
        self.bus.on(ident, on_ident)
        self.audio_service.handle_speak(message_with_ident)
        self.assertEqual(msg, message_with_ident)
        on_ident.assert_called_once()

        # Test `speak_ident`
        speak_ident = time()
        message_with_speak_ident = Message("speak",
                                           {"utterance": "with speak ident",
                                            "ident": ident,
                                            "speak_ident": speak_ident},
                                           {"destination": ["audio"]})
        on_speak_ident = Mock()
        self.bus.on(speak_ident, on_speak_ident)
        self.audio_service.handle_speak(message_with_speak_ident)
        self.assertEqual(msg, message_with_speak_ident)
        on_ident.assert_called_once()
        on_speak_ident.assert_called_once()

        self.audio_service.execute_tts = real_method

    def test_get_tts_supported_languages(self):
        real_tts = self.audio_service.tts
        resp = self.bus.wait_for_response(Message(
            "ovos.languages.tts", {}, {'ctx': True}
        ))
        self.assertIsInstance(resp, Message)
        self.assertTrue(resp.context.get('ctx'))

        self.assertEqual(resp.data['langs'],
                         list(real_tts.available_languages) or ['en-us'])

        mock_languages = ('en-us', 'es', 'fr-fr', 'fr-ca')
        from ovos_plugin_manager.templates.tts import TTS

        class MockTTS(TTS):
            def __init__(self):
                super(MockTTS, self).__init__()

            @property
            def available_languages(self):
                return mock_languages

            def execute(self, *args, **kwargs):
                pass

        mock_tts = MockTTS()
        self.audio_service.tts = mock_tts
        resp = self.bus.wait_for_response(Message(
            "ovos.languages.tts", {}, {'ctx': True}
        ))
        self.assertEqual(resp.data['langs'], list(mock_languages))

        self.audio_service.tts = real_tts


if __name__ == '__main__':
    unittest.main()
