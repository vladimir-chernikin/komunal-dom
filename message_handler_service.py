#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
MessageHandlerService - РµРґРёРЅС‹Р№ РјРёРєСЂРѕСЃРµСЂРІРёСЃ РѕР±СЂР°Р±РѕС‚РєРё СЃРѕРѕР±С‰РµРЅРёР№ РёР· РІСЃРµС… РєР°РЅР°Р»РѕРІ

РџСЂРёРЅРёРјР°РµС‚ СЃРѕРѕР±С‰РµРЅРёСЏ РёР·:
- Telegram
- WhatsApp
- РњРµСЃСЃРµРЅРґР¶РµСЂ РњР°РєСЃ
- Р’РµР±-СЃР°Р№С‚ (Django)
- РўРµСЃС‚РѕРІС‹Р№ Р±РѕС‚-РёРјРёС‚Р°С‚РѕСЂ
- Р“РѕР»РѕСЃРѕРІРѕР№ С‚СЂР°РЅСЃРєСЂРёР±Р°С‚РѕСЂ

Р›РѕРіРёСЂСѓРµС‚ РІСЃРµ СЃРѕРѕР±С‰РµРЅРёСЏ РІ Р‘Р” Рё РїРµСЂРµРґР°РµС‚ РІ MainAgent РґР»СЏ РѕР±СЂР°Р±РѕС‚РєРё
"""

import logging
import uuid
import asyncio
import re
from typing import Dict, Optional, Any
from datetime import datetime
from asgiref.sync import sync_to_async

from message_handler_intake_helpers import (
    build_intake_context,
    format_address,
    get_last_bot_metadata_from_history,
    merge_result_metadata,
    message_is_address_only,
)

logger = logging.getLogger(__name__)


class MessageHandlerService:
    """Р•РґРёРЅС‹Р№ СЃРµСЂРІРёСЃ РѕР±СЂР°Р±РѕС‚РєРё СЃРѕРѕР±С‰РµРЅРёР№ РёР· РІСЃРµС… РєР°РЅР°Р»РѕРІ"""

    def __init__(self, main_agent=None):
        """
        РРЅРёС†РёР°Р»РёР·Р°С†РёСЏ СЃРµСЂРІРёСЃР°

        Args:
            main_agent: Р­РєР·РµРјРїР»СЏСЂ MainAgent РґР»СЏ РѕР±СЂР°Р±РѕС‚РєРё СЃРѕРѕР±С‰РµРЅРёР№
        """
        self.main_agent = main_agent

        # РРЅРёС†РёР°Р»РёР·РёСЂСѓРµРј MessageCleanerService
        try:
            from message_cleaner_service import MessageCleanerService
            # РџРµСЂРµРґР°РµРј ai_agent РёР· MainAgent РґР»СЏ LLM-РѕС‡РёСЃС‚РєРё
            ai_agent = main_agent.ai_agent if main_agent else None
            self.message_cleaner = MessageCleanerService(ai_agent_service=ai_agent)
            logger.info("MessageCleanerService РёРЅРёС†РёР°Р»РёР·РёСЂРѕРІР°РЅ РІ MessageHandlerService")
        except ImportError:
            self.message_cleaner = None
            logger.warning("MessageCleanerService РЅРµ РЅР°Р№РґРµРЅ, РѕС‡РёСЃС‚РєР° СЃРѕРѕР±С‰РµРЅРёР№ РѕС‚РєР»СЋС‡РµРЅР°")

        try:
            from address_extractor_service import AddressExtractor

            self.address_extractor = AddressExtractor()
        except ImportError:
            self.address_extractor = None
            logger.warning("AddressExtractor unavailable in MessageHandlerService")

        try:
            from work_orders.intake_service import ChatIntakeService

            self.chat_intake_service = ChatIntakeService()
        except ImportError:
            self.chat_intake_service = None
            logger.warning("ChatIntakeService unavailable in MessageHandlerService")

        logger.info("MessageHandlerService РёРЅРёС†РёР°Р»РёР·РёСЂРѕРІР°РЅ")

    async def handle_incoming_message(
        self,
        text: str,
        user_id: str,
        channel: str = 'telegram',
        message_id: Optional[str] = None,
        session_id: Optional[str] = None,
        metadata: Optional[Dict] = None,
        django_user_id: Optional[int] = None
    ) -> Dict:
        """
        РћР±СЂР°Р±РѕС‚РєР° РІС…РѕРґСЏС‰РµРіРѕ СЃРѕРѕР±С‰РµРЅРёСЏ РёР· Р»СЋР±РѕРіРѕ РєР°РЅР°Р»Р°

        Args:
            text: РўРµРєСЃС‚ СЃРѕРѕР±С‰РµРЅРёСЏ
            user_id: ID РїРѕР»СЊР·РѕРІР°С‚РµР»СЏ РІ РєР°РЅР°Р»Рµ
            channel: РљР°РЅР°Р» СЃРІСЏР·Рё (telegram, whatsapp, web, test_bot, transcriber)
            message_id: ID СЃРѕРѕР±С‰РµРЅРёСЏ РІ РєР°РЅР°Р»Рµ
            session_id: ID СЃРµСЃСЃРёРё РґРёР°Р»РѕРіР° (РµСЃР»Рё None, СЃРѕР·РґР°РµС‚СЃСЏ/РїСЂРѕРґР»РµРІР°РµС‚СЃСЏ Р°РІС‚РѕРјР°С‚РёС‡РµСЃРєРё)
            metadata: Р”РѕРїРѕР»РЅРёС‚РµР»СЊРЅС‹Рµ РјРµС‚Р°РґР°РЅРЅС‹Рµ РѕС‚ РєР°РЅР°Р»Р°
            django_user_id: ID РїРѕР»СЊР·РѕРІР°С‚РµР»СЏ Django (РµСЃР»Рё РµСЃС‚СЊ)

        Returns:
            Dict: Р РµР·СѓР»СЊС‚Р°С‚ РѕР±СЂР°Р±РѕС‚РєРё СЃ РѕС‚РІРµС‚РѕРј Р±РѕС‚Р°
                {
                    'status': 'success' | 'error',
                    'response': str,  # РћС‚РІРµС‚ Р±РѕС‚Р°
                    'message_log_id': int,  # ID Р·Р°РїРёСЃР°РЅРЅРѕРіРѕ СЃРѕРѕР±С‰РµРЅРёСЏ
                    'session_id': str,  # ID СЃРµСЃСЃРёРё
                    'service_detected': Optional[dict]  # Р•СЃР»Рё СѓСЃР»СѓРіР° РѕРїСЂРµРґРµР»РµРЅР°
                }
        """
        try:
            # РРЎРџР РђР’Р›Р•РќРћ (2026-03-04): РРЅРёС†РёР°Р»РёР·РёСЂСѓРµРј PerformanceTracer РґР»СЏ С‚СЂРµРєРёРЅРіР° РІСЂРµРјРµРЅРё
            from performance_tracer import PerformanceTracer
            tracer = PerformanceTracer(session_id=session_id)
            tracer.start("total_request")

            # Р“РµРЅРµСЂРёСЂСѓРµРј СѓРЅРёРєР°Р»СЊРЅС‹Рµ ID РµСЃР»Рё РЅРµ РїРµСЂРµРґР°РЅС‹
            if not message_id:
                message_id = f"{channel}_{uuid.uuid4().hex[:16]}"

            # РРЎРџР РђР’Р›Р•РќРћ (2025-12-28): РЈРјРЅРѕРµ СѓРїСЂР°РІР»РµРЅРёРµ СЃРµСЃСЃРёСЏРјРё
            if not session_id:
                # РџСЂРѕРІРµСЂСЏРµРј: РµСЃР»Рё СЌС‚Рѕ РїСЂРёРІРµС‚СЃС‚РІРёРµ - СЃРѕР·РґР°РµРј РќРћР’РЈР® СЃРµСЃСЃРёСЋ
                is_greeting = False
                if self.message_cleaner and self.message_cleaner.is_greeting_only(text):
                    is_greeting = True
                    # Р“РµРЅРµСЂРёСЂСѓРµРј СѓРЅРёРєР°Р»СЊРЅС‹Р№ session_id СЃ timestamp
                    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                    session_id = f"{channel}_{user_id}_{timestamp}"
                    logger.info(f"РџСЂРёРІРµС‚СЃС‚РІРёРµ detected в†’ СЃРѕР·РґР°РЅР° РЅРѕРІР°СЏ СЃРµСЃСЃРёСЏ: {session_id}")
                else:
                    # РРЎРџР РђР’Р›Р•РќРћ: РС‰РµРј Р°РєС‚РёРІРЅСѓСЋ СЃРµСЃСЃРёСЋ (РЅРµ СЃС‚Р°СЂС€Рµ 1 С‡Р°СЃР°)
                    session_id = await self._find_or_create_active_session(user_id, channel)

            logger.info(
                f"MessageHandler: Р’С…РѕРґСЏС‰РµРµ СЃРѕРѕР±С‰РµРЅРёРµ РёР· {channel} | "
                f"User: {user_id} | Session: {session_id} | Text: '{text[:50]}...'"
            )

            # РРЎРџР РђР’Р›Р•РќРћ (2026-03-05): Р›РѕРіРёСЂСѓРµРј РІС…РѕРґСЏС‰РёР№ metadata РґР»СЏ РѕС‚Р»Р°РґРєРё
            if metadata:
                logger.info(f"[DEBUG] Р’С…РѕРґСЏС‰РёР№ metadata: {list(metadata.keys())}, api_info={metadata.get('api_info')}")
            else:
                logger.warning(f"[DEBUG] Р’С…РѕРґСЏС‰РёР№ metadata РџРћРЈРЎРўРћ!")

            # 1. Р›РѕРіРёСЂСѓРµРј РІС…РѕРґСЏС‰РµРµ СЃРѕРѕР±С‰РµРЅРёРµ РІ Р‘D
            message_log = await self._log_message(
                text=text,
                user_id=user_id,
                channel=channel,
                message_id=message_id,
                session_id=session_id,
                direction='inbound',
                metadata=metadata or {},
                django_user_id=django_user_id
            )

            # РРЎРџР РђР’Р›Р•РќРћ (2026-03-05): РЇРІРЅРѕ СЃРѕС…СЂР°РЅСЏРµРј api_info Рё client_system РІ metadata СЃСЂР°Р·Сѓ РїРѕСЃР»Рµ Р»РѕРіРёСЂРѕРІР°РЅРёСЏ
            # Р­С‚Рѕ РіР°СЂР°РЅС‚РёСЂСѓРµС‚ С‡С‚Рѕ СЌС‚Рё РїРѕР»СЏ РЅРµ РїРѕС‚РµСЂСЏСЋС‚СЃСЏ РїСЂРё РїРѕСЃР»РµРґСѓСЋС‰РёС… РѕР±РЅРѕРІР»РµРЅРёСЏС… С‡РµСЂРµР· MainAgent
            inbound_message_id = message_log.get('id') if isinstance(message_log, dict) else None
            if metadata and isinstance(metadata, dict) and inbound_message_id:
                preserved_fields = {}
                if 'api_info' in metadata:
                    preserved_fields['api_info'] = metadata['api_info']
                if 'client_system' in metadata:
                    preserved_fields['client_system'] = metadata['client_system']

                if preserved_fields:
                    logger.info(f"[DEBUG] РЎРѕС…СЂР°РЅСЏРµРј api_info/client_system РІ metadata id={inbound_message_id}: {list(preserved_fields.keys())}")
                    await self._update_message_metadata(inbound_message_id, preserved_fields)

            # 2. РџРѕР»СѓС‡Р°РµРј РёСЃС‚РѕСЂРёСЋ РґРёР°Р»РѕРіР° РґР»СЏ РєРѕРЅС‚РµРєСЃС‚Р°
            dialog_history = await self._get_dialog_history(session_id, limit=10)

            # 2.5. РћС‡РёС‰Р°РµРј СЃРѕРѕР±С‰РµРЅРёРµ РѕС‚ РјСѓСЃРѕСЂР° (РїСЂРёРІРµС‚С‹, insignificant words)
            search_text = text
            if self.message_cleaner:
                cleaned_text, clean_metadata = await self.message_cleaner.clean_message(text)
                search_text = cleaned_text

                # РџСЂРѕРІРµСЂСЏРµРј: РµСЃР»Рё СЃРѕРѕР±С‰РµРЅРёРµ С‚РѕР»СЊРєРѕ РїСЂРёРІРµС‚СЃС‚РІРёРµ - РѕС‚РІРµС‡Р°РµРј РїСЂРёРІРµС‚СЃС‚РІРёРµРј
                # РРЎРџР РђР’Р›Р•РќРћ (2026-01-06): РќР• Р»РѕРіРёСЂСѓРµРј Р·РґРµСЃСЊ - Р±СѓРґРµС‚ Р·Р°Р»РѕРіРёСЂРѕРІР°РЅРѕ РЅРёР¶Рµ (СЃС‚СЂРѕРєРё 247-255)
                if self.message_cleaner.is_greeting_only(text):
                    logger.info(f"РћР±РЅР°СЂСѓР¶РµРЅРѕ С‡РёСЃС‚РѕРµ РїСЂРёРІРµС‚СЃС‚РІРёРµ РѕС‚ user {user_id}")

                    return {
                        'status': 'success',
                        'response': "Р—РґСЂР°РІСЃС‚РІСѓР№С‚Рµ! РћРїРёС€РёС‚Рµ РІР°С€Сѓ РїСЂРѕР±Р»РµРјСѓ, Рё СЏ РїРѕРїСЂРѕР±СѓСЋ РїРѕРјРѕС‡СЊ.",
                        'message_log_id': message_log.get('id') if isinstance(message_log, dict) else None,
                        'session_id': session_id,
                        'is_greeting': True
                    }

                if clean_metadata.get('removed_greeting') or clean_metadata.get('removed_fillers'):
                    logger.info(f"РЎРѕРѕР±С‰РµРЅРёРµ РѕС‡РёС‰РµРЅРѕ: СѓРґР°Р»РµРЅРѕ {clean_metadata}")

            last_bot_metadata = self._get_last_bot_metadata_from_history(dialog_history)
            stored_intake_context = last_bot_metadata.get('intake_context') if isinstance(last_bot_metadata, dict) else {}
            if not isinstance(stored_intake_context, dict):
                stored_intake_context = {}
            address_components = stored_intake_context.get('address_components') or last_bot_metadata.get('address_components') or {}
            address_validation = stored_intake_context.get('address_validation') or last_bot_metadata.get('address_validation') or {}
            intake_context = dict(stored_intake_context)

            # 3. РџР РћР’Р•Р РљРђ: РЇРІР»СЏРµС‚СЃСЏ Р»Рё СЌС‚Рѕ РѕС‚РІРµС‚РѕРј РЅР° РїРѕРґС‚РІРµСЂР¶РґРµРЅРёРµ?
            confirmation_result = await self._check_confirmation_response(
                text=search_text,
                original_text=text,
                dialog_history=dialog_history,
                session_id=session_id,
                channel=channel,
                user_id=user_id,
                django_user_id=django_user_id,
                message_log_id=message_log.get('id') if isinstance(message_log, dict) else None,
                source_metadata=metadata or {},
            )

            if confirmation_result.get('is_confirmation_response'):
                # Р­С‚Рѕ РѕС‚РІРµС‚ РЅР° РїРѕРґС‚РІРµСЂР¶РґРµРЅРёРµ - РѕР±СЂР°Р±Р°С‚С‹РІР°РµРј РѕС‚РґРµР»СЊРЅРѕ
                result = confirmation_result.get('result')
            else:
                result = None

                if self.address_extractor:
                    address_components = self.address_extractor.extract_address_components(
                        search_text,
                        context_memory=address_components,
                    )
                    address_validation = self.address_extractor.validate_and_match_to_db(address_components)
                    intake_context = self._build_intake_context(
                        existing_context=intake_context,
                        address_components=address_components,
                        address_validation=address_validation,
                    )

                    match_status = address_validation.get('match_status')
                    if match_status in {'incomplete', 'not_found'}:
                        clarification = self.address_extractor.ask_clarification_if_needed(
                            address_components,
                            address_validation,
                        )
                        result = {
                            'status': 'ADDRESS_REQUIRED',
                            'message': clarification.get('message') or 'РќР°РїРёС€РёС‚Рµ, РїРѕР¶Р°Р»СѓР№СЃС‚Р°, Р°РґСЂРµСЃ: СѓР»РёС†Сѓ Рё РЅРѕРјРµСЂ РґРѕРјР°.',
                            '_metadata': {
                                'address_components': address_components,
                                'address_validation': address_validation,
                                'intake_context': intake_context,
                            },
                        }
                    elif match_status == 'not_serviced':
                        result = {
                            'status': 'ADDRESS_NOT_SERVICED',
                            'message': 'РђРґСЂРµСЃ СЃСѓС‰РµСЃС‚РІСѓРµС‚, РЅРѕ РїРѕРєР° РЅРµ РїСЂРёРІСЏР·Р°РЅ Рє РѕР±СЃР»СѓР¶РёРІР°РµРјРѕРјСѓ РѕР±СЉРµРєС‚Сѓ. РџСЂРѕРІРµСЂСЊС‚Рµ Р°РґСЂРµСЃ РёР»Рё СЃРІСЏР¶РёС‚РµСЃСЊ СЃ РѕРїРµСЂР°С‚РѕСЂРѕРј.',
                            '_metadata': {
                                'address_components': address_components,
                                'address_validation': address_validation,
                                'intake_context': intake_context,
                            },
                        }
                    elif self._message_is_address_only(search_text, address_components):
                        result = {
                            'status': 'ADDRESS_ACCEPTED',
                            'message': f"РђРґСЂРµСЃ РЅР°С€Р»Р°: {address_validation.get('address_full')}. Р§С‚Рѕ СЃР»СѓС‡РёР»РѕСЃСЊ?",
                            '_metadata': {
                                'address_components': address_components,
                                'address_validation': address_validation,
                                'intake_context': intake_context,
                            },
                        }

                if result is None:
                    # 4. РћР±С‹С‡РЅР°СЏ РѕР±СЂР°Р±РѕС‚РєР° С‡РµСЂРµР· MainAgent
                    if not self.main_agent:
                        logger.warning("MessageHandler: MainAgent РЅРµ РёРЅРёС†РёР°Р»РёР·РёСЂРѕРІР°РЅ")
                        return {
                            'status': 'error',
                            'error': 'MainAgent not available',
                            'session_id': session_id,
                            'message_log_id': message_log.get('id') if isinstance(message_log, dict) else None
                        }

                    user_messages = [m for m in dialog_history if m.get('role') == 'user']
                    non_greeting_messages = [
                        m for m in user_messages
                        if not self.message_cleaner or not self.message_cleaner.is_greeting_only(m.get('text', ''))
                    ]
                    is_followup = len(non_greeting_messages) >= 1

                    if is_followup:
                        logger.info(f"MessageHandler: is_followup=True (РєРѕРЅС‚РµРєСЃС‚РЅС‹С… СЃРѕРѕР±С‰РµРЅРёР№: {len(non_greeting_messages)})")

                    established_filters = None
                    txtPrb = None
                    txt_stop_questions = []
                    if dialog_history and len(dialog_history) > 0:
                        for msg in reversed(dialog_history):
                            if msg.get('role') == 'bot':
                                metadata = msg.get('metadata', {})
                                if isinstance(metadata, dict):
                                    if 'established_filters' in metadata:
                                        established_filters = metadata['established_filters']
                                        logger.info(f"[DEBUG] РР·РІР»РµС‡РµРЅС‹ established_filters РёР· РёСЃС‚РѕСЂРёРё: {list(established_filters.keys()) if established_filters else 'None'}")
                                    if 'txtPrb' in metadata:
                                        txtPrb = metadata['txtPrb']
                                        logger.info(f"[DEBUG] РР·РІР»РµС‡РµРЅ txtPrb РёР· РёСЃС‚РѕСЂРёРё: '{txtPrb[:80] if txtPrb else '(РїСѓСЃС‚Рѕ)'}...'")
                                    if 'txtStopQ' in metadata:
                                        txt_stop_questions = metadata['txtStopQ']
                                        logger.info(f"[DEBUG] РР·РІР»РµС‡РµРЅС‹ txtStopQ РёР· РёСЃС‚РѕСЂРёРё: {len(txt_stop_questions)} РІРѕРїСЂРѕСЃРѕРІ")
                                        break

                    logger.info(f"[DEBUG] dialog_history РџР•Р Р•Р” РїРµСЂРµРґР°С‡РµР№ РІ MainAgent: {len(dialog_history)} СЃРѕРѕР±С‰РµРЅРёР№")
                    if dialog_history and len(dialog_history) > 0:
                        for i, msg in enumerate(dialog_history[-3:], 1):
                            logger.info(f"  {i}. [{msg.get('role')}] {msg.get('text', '')[:50]}")

                    result = await self.main_agent.process_service_detection(
                        message_text=search_text,
                        user_context={
                            'original_message': text,
                            'user_id': user_id,
                            'channel': channel,
                            'session_id': session_id,
                            'message_id': message_log.get('id') if isinstance(message_log, dict) else None,
                            'dialog_history': dialog_history,
                            'is_followup': is_followup,
                            'cleaned_message': search_text,
                            'established_filters': established_filters,
                            'txtPrb': txtPrb,
                            'txtStopQ': txt_stop_questions,
                            'context_memory': address_components,
                            'address_validation': address_validation,
                            'intake_context': intake_context,
                            'performance_tracer': tracer
                        }
                    )
                    result = self._merge_result_metadata(
                        result,
                        address_components=address_components,
                        address_validation=address_validation,
                        intake_context=intake_context,
                    )

            # РРЎРџР РђР’Р›Р•РќРћ (2026-01-06): РћР±РЅРѕРІР»СЏРµРј metadata РґР»СЏ inbound СЃРѕРѕР±С‰РµРЅРёСЏ СЃ txtPrb
            # РљР РРўРР§Р•РЎРљР Р’РђР–РќРћ: TraceReportService С‡РёС‚Р°РµС‚ metadata РёР· Р‘Р”!
            logger.info(f"[METADATA CHECK] _metadata РІ result: {('_metadata' in result)}, message_log is dict: {isinstance(message_log, dict)}")
            if '_metadata' in result and isinstance(message_log, dict):
                inbound_message_id = message_log.get('id')
                logger.info(f"[METADATA CHECK] inbound_message_id={inbound_message_id}, condition: {inbound_message_id and inbound_message_id > 0}")
                if inbound_message_id and inbound_message_id > 0:
                    try:
                        # РРЎРџР РђР’Р›Р•РќРћ (2026-02-17): РљР РРўРР§Р•РЎРљРР™ Р›РћР“ (Р‘Р•Р—РћРџРђРЎРќР«Р™)
                        metadata_obj = result.get('_metadata', {})
                        txtPrb_val = metadata_obj.get('txtPrb', '(РЅРµС‚)') if isinstance(metadata_obj, dict) else '(РЅРµС‚)'
                        logger.info(f"[CRITICAL] РћР±РЅРѕРІР»СЏРµРј metadata РґР»СЏ inbound id={inbound_message_id}, txtPrb='{str(txtPrb_val)[:60]}...'")
                        await self._update_message_metadata(
                            message_id=inbound_message_id,
                            metadata=result['_metadata']
                        )
                        logger.info(f"[DEBUG] вњ… Metadata РѕР±РЅРѕРІР»РµРЅР° РґР»СЏ inbound СЃРѕРѕР±С‰РµРЅРёСЏ id={inbound_message_id}")
                    except Exception as e:
                        logger.warning(f"[WARNING] РќРµ СѓРґР°Р»РѕСЃСЊ РѕР±РЅРѕРІРёС‚СЊ metadata РґР»СЏ inbound: {e}")
                        logger.error(f"[ERROR] Traceback:", exc_info=True)
                else:
                    logger.warning(f"[WARNING] inbound_message_id={inbound_message_id}, РѕР±РЅРѕРІР»РµРЅРёРµ РїСЂРѕРїСѓС‰РµРЅРѕ")
            else:
                logger.warning(f"[WARNING] _metadata РЅРµ РІ result РёР»Рё message_log not dict: _metadata={('_metadata' in result)}, is_dict={isinstance(message_log, dict)}")

            # 5. Р¤РѕСЂРјРёСЂСѓРµРј РѕС‚РІРµС‚ Р±РѕС‚Р°
            bot_response = self._extract_bot_response(result)

            # 6. Р›РѕРіРёСЂСѓРµРј РёСЃС…РѕРґСЏС‰РµРµ СЃРѕРѕР±С‰РµРЅРёРµ (РѕС‚РІРµС‚ Р±РѕС‚Р°)
            # РРЎРџР РђР’Р›Р•РќРћ (2025-12-27): Р”РѕР±Р°РІР»СЏРµРј txtPrb Рё metadata РІ outbound СЃРѕРѕР±С‰РµРЅРёСЏ
            if bot_response:
                # РРЎРџР РђР’Р›Р•РќРћ (2026-01-05): РћС‚Р»Р°РґРѕС‡РЅС‹Р№ Р»РѕРі - РїСЂРѕРІРµСЂСЏРµРј result Рё _metadata
                logger.info(f"[DEBUG] result РєР»СЋС‡Рё: {list(result.keys())}")
                logger.info(f"[DEBUG] '_metadata' РІ result: {'_metadata' in result}")
                if '_metadata' in result:
                    logger.info(f"[DEBUG] _metadata РєР»СЋС‡Рё: {list(result['_metadata'].keys())}")
                    logger.info(f"[DEBUG] 'txtPrb' РІ _metadata: {'txtPrb' in result['_metadata']}")
                    if 'txtPrb' in result['_metadata']:
                        logger.info(f"[DEBUG] txtPrb Р·РЅР°С‡РµРЅРёРµ: '{result['_metadata']['txtPrb']}'")

                # Р¤РѕСЂРјРёСЂСѓРµРј metadata РґР»СЏ outbound СЃРѕРѕР±С‰РµРЅРёСЏ
                outbound_metadata = {'service_result': result}

                # РРЎРџР РђР’Р›Р•РќРћ (2026-03-05): РЎРѕС…СЂР°РЅСЏРµРј api_info Рё client_system РёР· РёСЃС…РѕРґРЅРѕРіРѕ metadata
                if metadata and isinstance(metadata, dict):
                    logger.info(f"[DEBUG] metadata РЅР° РІС…РѕРґРµ: {list(metadata.keys())}")
                    if 'api_info' in metadata:
                        outbound_metadata['api_info'] = metadata['api_info']
                        logger.info(f"[DEBUG] вњ… api_info СЃРєРѕРїРёСЂРѕРІР°РЅ: {metadata['api_info']}")
                    if 'client_system' in metadata:
                        outbound_metadata['client_system'] = metadata['client_system']
                        logger.info(f"[DEBUG] вњ… client_system СЃРєРѕРїРёСЂРѕРІР°РЅ: {metadata['client_system']}")
                else:
                    logger.warning(f"[DEBUG] вљ пёЏ metadata РѕС‚СЃСѓС‚СЃС‚РІСѓРµС‚ РёР»Рё РЅРµ dict: type={type(metadata)}, value={metadata}")

                # Р”РѕР±Р°РІР»СЏРµРј txtPrb РµСЃР»Рё РµСЃС‚СЊ РІ result
                if '_metadata' in result and 'txtPrb' in result['_metadata']:
                    outbound_metadata['txtPrb'] = result['_metadata']['txtPrb']
                    # РРЎРџР РђР’Р›Р•РќРћ (2026-02-24): accumulated_fields РЈР”РђР›РЃРќ
                    outbound_metadata['established_filters'] = result['_metadata'].get('established_filters', {})
                    # РРЎРџР РђР’Р›Р•РќРћ (2026-02-04): Р”РѕР±Р°РІР»СЏРµРј txtStopQ (Р·Р°РїСЂРµС‰РµРЅРЅС‹Рµ РІРѕРїСЂРѕСЃС‹)
                    outbound_metadata['txtStopQ'] = result['_metadata'].get('txtStopQ', [])
                    logger.info(f"[DEBUG] вњ… txtPrb Р”РћР‘РђР’Р›Р•Рќ РІ outbound_metadata: '{outbound_metadata['txtPrb']}'")
                    logger.info(f"[DEBUG] вњ… txtStopQ Р”РћР‘РђР’Р›Р•Рќ РІ outbound_metadata: {len(outbound_metadata.get('txtStopQ', []))} РІРѕРїСЂРѕСЃРѕРІ")
                else:
                    logger.warning(f"[WARNING] вљ пёЏ txtPrb РќР• Р”РћР‘РђР’Р›Р•Рќ РІ outbound_metadata!")

                # РРЎРџР РђР’Р›Р•РќРћ (2026-01-06): Р›РѕРіРёСЂСѓРµРј outbound РґР»СЏ Р’РЎР•РҐ РєР°РЅР°Р»РѕРІ
                # РљР РРўРР§Р•РЎРљР Р’РђР–РќРћ: test_bot_simulator Рё РґСЂСѓРіРёРµ РєР°РЅР°Р»С‹ С‚РѕР¶Рµ РЅСѓР¶РґР°СЋС‚СЃСЏ РІ Р»РѕРіРёСЂРѕРІР°РЅРёРё!

                # РРЎРџР РђР’Р›Р•РќРћ (2026-03-04): Р—Р°РІРµСЂС€Р°РµРј С‚СЂРµРєРёРЅРі Р”Рћ Р»РѕРіРёСЂРѕРІР°РЅРёСЏ outbound
                tracer.end("total_request")
                performance_data = tracer.save_to_metadata()

                # РРЎРџР РђР’Р›Р•РќРћ (2026-03-10): РћС‚Р»Р°РґРѕС‡РЅС‹Р№ Р»РѕРі РґР»СЏ РїСЂРѕРІРµСЂРєРё performance_data
                logger.info(f"[DEBUG] performance_data keys: {list(performance_data.keys()) if performance_data else 'None'}")
                logger.info(f"[DEBUG] performance РІ performance_data: {'performance' in performance_data if performance_data else False}")
                if performance_data and 'performance' in performance_data:
                    logger.info(f"[DEBUG] performance РєР»СЋС‡Рё: {list(performance_data['performance'].keys())}")

                # Р”РѕР±Р°РІР»СЏРµРј performance РґР°РЅРЅС‹Рµ РІ outbound_metadata
                if performance_data and 'performance' in performance_data:
                    outbound_metadata['performance'] = performance_data['performance']
                    logger.info(f"[DEBUG] вњ… Performance РґР°РЅРЅС‹Рµ РґРѕР±Р°РІР»РµРЅС‹ РІ outbound_metadata: {len(performance_data.get('performance', {}).get('stages', []))} СЌС‚Р°РїРѕРІ")
                else:
                    logger.warning(f"[WARNING] вљ пёЏ Performance РґР°РЅРЅС‹Рµ РќР• РґРѕР±Р°РІР»РµРЅС‹: performance_data={performance_data}")

                await self._log_message(
                    text=bot_response,
                    user_id=user_id,
                    channel=channel,
                    message_id=f"bot_{uuid.uuid4().hex[:16]}",
                    session_id=session_id,
                    direction='outbound',
                    metadata=outbound_metadata
                )

            logger.info(
                f"MessageHandler: РћР±СЂР°Р±РѕС‚РєР° Р·Р°РІРµСЂС€РµРЅР° | "
                f"Session: {session_id} | Status: {result.get('status')} | "
                f"Response: '{bot_response[:50] if bot_response else 'NO'}...'"
            )

            return {
                'status': 'success',
                'response': bot_response,
                'raw_result': result,
                'message_log_id': message_log.get('id') if isinstance(message_log, dict) else None,
                'session_id': session_id,
                'service_detected': result.get('service_id') if result.get('status') == 'SUCCESS' else None,
                '_metadata': result.get('_metadata', {}),  # РРЎРџР РђР’Р›Р•РќРћ (2026-02-17): РџРµСЂРµРґР°РµРј metadata РІ С„РёРЅР°Р»СЊРЅС‹Р№ РѕС‚РІРµС‚
                'performance': performance_data.get('performance', {})  # РРЎРџР РђР’Р›Р•РќРћ (2026-03-04): Р”РѕР±Р°РІР»СЏРµРј performance РґР°РЅРЅС‹Рµ
            }

        except Exception as e:
            logger.error(f"MessageHandler: РћС€РёР±РєР° РѕР±СЂР°Р±РѕС‚РєРё СЃРѕРѕР±С‰РµРЅРёСЏ: {e}")
            return {
                'status': 'error',
                'error': str(e),
                'session_id': session_id if session_id else f"{channel}_{user_id}"
            }

    async def _find_or_create_active_session(self, user_id: str, channel: str) -> str:
        """
        РС‰РµС‚ Р°РєС‚РёРІРЅСѓСЋ СЃРµСЃСЃРёСЋ РїРѕР»СЊР·РѕРІР°С‚РµР»СЏ (РЅРµ СЃС‚Р°СЂС€Рµ 1 С‡Р°СЃР°) РёР»Рё СЃРѕР·РґР°РµС‚ РЅРѕРІСѓСЋ

        РРЎРџР РђР’Р›Р•РќРћ (2025-12-28):
        - РџСЂРѕРІРµСЂСЏРµС‚ РїРѕСЃР»РµРґРЅСЋСЋ СЃРµСЃСЃРёСЋ РїРѕР»СЊР·РѕРІР°С‚РµР»СЏ
        - Р•СЃР»Рё РїРѕСЃР»РµРґРЅСЏСЏ СЃРµСЃСЃРёСЏ РЅРµ СЃС‚Р°СЂС€Рµ 1 С‡Р°СЃР° - РїСЂРѕРґРѕР»Р¶Р°РµС‚ РµС‘
        - РРЅР°С‡Рµ СЃРѕР·РґР°РµС‚ РЅРѕРІСѓСЋ СЃРµСЃСЃРёСЋ

        Args:
            user_id: ID РїРѕР»СЊР·РѕРІР°С‚РµР»СЏ РІ РєР°РЅР°Р»Рµ
            channel: РљР°РЅР°Р» СЃРІСЏР·Рё

        Returns:
            str: ID СЃРµСЃСЃРёРё (СЃСѓС‰РµСЃС‚РІСѓСЋС‰РµР№ РёР»Рё РЅРѕРІРѕР№)
        """
        try:
            from message_handler.models import MessageLog
            from django.utils import timezone
            from datetime import timedelta

            def find_session_sync():
                # РС‰РµРј РїРѕСЃР»РµРґРЅСЋСЋ СЃРµСЃСЃРёСЋ РїРѕР»СЊР·РѕРІР°С‚РµР»СЏ
                last_msg = MessageLog.objects.filter(
                    user_id=user_id,
                    channel=channel
                ).order_by('-timestamp').first()

                if not last_msg:
                    # РќРµС‚ СЃРѕРѕР±С‰РµРЅРёР№ - СЃРѕР·РґР°РµРј РЅРѕРІСѓСЋ СЃРµСЃСЃРёСЋ
                    return None

                # РџСЂРѕРІРµСЂСЏРµРј РІРѕР·СЂР°СЃС‚ РїРѕСЃР»РµРґРЅРµРіРѕ СЃРѕРѕР±С‰РµРЅРёСЏ
                now = timezone.now()
                session_age = now - last_msg.timestamp

                # Р•СЃР»Рё РїСЂРѕС€Р»Рѕ РјРµРЅСЊС€Рµ 1 С‡Р°СЃР° - РїСЂРѕРґРѕР»Р¶Р°РµРј СЌС‚Сѓ СЃРµСЃСЃРёСЋ
                if session_age < timedelta(hours=1):
                    logger.info(f"РђРєС‚РёРІРЅР°СЏ СЃРµСЃСЃРёСЏ РЅР°Р№РґРµРЅР°: {last_msg.session_id} (РІРѕР·СЂР°СЃС‚: {session_age.seconds // 60} РјРёРЅ)")
                    return last_msg.session_id

                # РЎРµСЃСЃРёСЏ СѓСЃС‚Р°СЂРµР»Р° - СЃРѕР·РґР°РµРј РЅРѕРІСѓСЋ
                logger.info(f"РџРѕСЃР»РµРґРЅСЏСЏ СЃРµСЃСЃРёСЏ СѓСЃС‚Р°СЂРµР»Р° ({session_age.seconds // 60} РјРёРЅ), СЃРѕР·РґР°РµРј РЅРѕРІСѓСЋ")
                return None

            existing_session_id = await sync_to_async(find_session_sync)()

            if existing_session_id:
                return existing_session_id

            # РЎРѕР·РґР°РµРј РЅРѕРІСѓСЋ СЃРµСЃСЃРёСЋ
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            new_session_id = f"{channel}_{user_id}_{timestamp}"
            logger.info(f"РЎРѕР·РґР°РЅР° РЅРѕРІР°СЏ СЃРµСЃСЃРёСЏ: {new_session_id}")
            return new_session_id

        except Exception as e:
            logger.error(f"РћС€РёР±РєР° РїРѕРёСЃРєР° Р°РєС‚РёРІРЅРѕР№ СЃРµСЃСЃРёРё: {e}")
            # Fallback: СЃРѕР·РґР°РµРј РЅРѕРІСѓСЋ СЃРµСЃСЃРёСЋ
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            return f"{channel}_{user_id}_{timestamp}"

    async def _log_message(
        self,
        text: str,
        user_id: str,
        channel: str,
        message_id: str,
        session_id: str,
        direction: str,
        metadata: Dict = None,
        django_user_id: Optional[int] = None,
        dialog_id: Optional[str] = None,
        confidence_score: Optional[float] = None,
        service_detected_id: Optional[int] = None,
        processing_stage: Optional[str] = None,
        processing_time_ms: Optional[int] = None,
        llm_provider: Optional[str] = None,
        llm_model: Optional[str] = None,
        tokens_used: Optional[int] = None,
        cost_rub: Optional[float] = None
    ) -> Dict:
        """
        Р›РѕРіРёСЂРѕРІР°РЅРёРµ СЃРѕРѕР±С‰РµРЅРёСЏ РІ dialog_logs

        РРЎРџР РђР’Р›Р•РќРћ (2026-01-03): РџРµСЂРµРїРёСЃР°РЅРѕ РЅР° РёСЃРїРѕР»СЊР·РѕРІР°РЅРёРµ dialog_logs
        Р’РјРµСЃС‚Рѕ message_handler_messagelog РёСЃРїРѕР»СЊР·СѓРµРј dialog_logs

        Returns:
            Dict: РЎРѕР·РґР°РЅРЅР°СЏ Р·Р°РїРёСЃСЊ СЃРѕРѕР±С‰РµРЅРёСЏ
        """
        try:
            from dialog_logger_service import get_dialog_logger

            dialog_logger = get_dialog_logger()

            # РљРѕРЅРІРµСЂС‚РёСЂСѓРµРј user_id РІ int РґР»СЏ dialog_logs
            user_id_int = int(user_id) if user_id.isdigit() else 0

            # РћРїСЂРµРґРµР»СЏРµРј message_type
            if direction == 'inbound':
                message_type = 'inbound'
            elif direction == 'outbound':
                message_type = 'outbound'
            else:
                message_type = 'system'

            # РРЎРџР РђР’Р›Р•РќРћ (2026-01-05): Р“РµРЅРµСЂРёСЂСѓРµРј UUID РёР· session_id РµСЃР»Рё РЅРµ РїРµСЂРµРґР°РЅ dialog_id
            final_dialog_id = dialog_id
            if not final_dialog_id:
                # Р•СЃР»Рё session_id СѓР¶Рµ UUID - РёСЃРїРѕР»СЊР·СѓРµРј РµРіРѕ
                import re
                uuid_pattern = r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
                if re.match(uuid_pattern, session_id.lower()):
                    final_dialog_id = session_id
                else:
                    # РРЅР°С‡Рµ РіРµРЅРµСЂРёСЂСѓРµРј UUID РёР· session_id (РґРµС‚РµСЂРјРёРЅРёСЂРѕРІР°РЅРѕ)
                    import hashlib
                    session_hash = hashlib.md5(session_id.encode()).hexdigest()
                    final_dialog_id = f"{session_hash[:8]}-{session_hash[8:12]}-{session_hash[12:16]}-{session_hash[16:20]}-{session_hash[20:32]}"

            # РРЎРџР РђР’Р›Р•РќРћ (2026-03-05): РћС‚Р»Р°РґРѕС‡РЅС‹Р№ РІС‹РІРѕРґ metadata
            final_metadata = {
                **(metadata or {}),
                'channel': channel,
                'message_id': message_id,
                'django_user_id': django_user_id
            }
            logger.info(f"[DEBUG] _log_message: metadata keys={list(final_metadata.keys())}, api_info={final_metadata.get('api_info')}")

            # Р›РѕРіРёСЂСѓРµРј С‡РµСЂРµР· DialogLoggerService
            # РРЎРџР РђР’Р›Р•РќРћ (2026-01-06): РџРѕР»СѓС‡Р°РµРј СЂРµР°Р»СЊРЅС‹Р№ ID СЃРѕР·РґР°РЅРЅРѕР№ Р·Р°РїРёСЃРё
            # РРЎРџР РђР’Р›Р•РќРћ (2026-03-05): РСЃРїРѕР»СЊР·СѓРµРј final_metadata (СЃ api_info)
            record_id = await dialog_logger.log_message(
                dialog_id=final_dialog_id,  # РРЎРџР РђР’Р›Р•РќРћ: РіР°СЂР°РЅС‚РёСЂРѕРІР°РЅРЅРѕ UUID
                user_id=user_id_int,
                message_type=message_type,
                message_content=text,
                processing_stage=processing_stage,
                confidence_score=confidence_score,
                service_detected_id=service_detected_id,
                processing_time_ms=processing_time_ms,
                llm_provider=llm_provider,
                llm_model=llm_model,
                tokens_used=tokens_used,
                cost_rub=cost_rub,
                metadata=final_metadata,  # РРЎРџР РђР’Р›Р•РќРћ (2026-03-05): final_metadata РІРјРµСЃС‚Рѕ {}
                # РРЎРџР РђР’Р›Р•РќРћ (2026-01-05): session_id, channel, direction, message_id Р”РћР›Р–РќР« Р±С‹С‚СЊ РѕС‚РґРµР»СЊРЅС‹РјРё РїР°СЂР°РјРµС‚СЂР°РјРё!
                session_id=session_id,
                channel=channel,
                direction=direction,
                message_id=message_id,
                django_user_id=django_user_id
            )

            # РРЎРџР РђР’Р›Р•РќРћ (2026-01-06): Р’РѕР·РІСЂР°С‰Р°РµРј СЂРµР°Р»СЊРЅС‹Р№ ID РёР· Р‘Р”
            return {
                'id': record_id if record_id else 0,
                'created_at': None
            }

        except Exception as e:
            logger.error(f"MessageHandler: РћС€РёР±РєР° Р»РѕРіРёСЂРѕРІР°РЅРёСЏ РІ dialog_logs: {e}")
            return {}

    async def _update_message_metadata(self, message_id: int, metadata: Dict) -> bool:
        """
        РћР±РЅРѕРІР»СЏРµС‚ metadata РґР»СЏ СЃРѕРѕР±С‰РµРЅРёСЏ РІ dialog_logs

        РРЎРџР РђР’Р›Р•РќРћ (2026-01-06): Р”РѕР±Р°РІР»РµРЅРѕ РґР»СЏ РѕР±РЅРѕРІР»РµРЅРёСЏ txtPrb РІ inbound СЃРѕРѕР±С‰РµРЅРёСЏС…

        Args:
            message_id: ID СЃРѕРѕР±С‰РµРЅРёСЏ РІ dialog_logs
            metadata: РќРѕРІС‹Рµ РјРµС‚Р°РґР°РЅРЅС‹Рµ (Р±СѓРґСѓС‚ РѕР±СЉРµРґРёРЅРµРЅС‹ СЃ СЃСѓС‰РµСЃС‚РІСѓСЋС‰РёРјРё)

        Returns:
            bool: True РµСЃР»Рё СѓСЃРїРµС€РЅРѕ, False РµСЃР»Рё РѕС€РёР±РєР°
        """
        try:
            from django.db import connection

            def update_sync():
                with connection.cursor() as cursor:
                    # Р§РёС‚Р°РµРј СЃСѓС‰РµСЃС‚РІСѓСЋС‰СѓСЋ metadata
                    cursor.execute("""
                        SELECT metadata FROM dialog_logs WHERE id = %s
                    """, [message_id])

                    row = cursor.fetchone()
                    if not row:
                        logger.warning(f"РЎРѕРѕР±С‰РµРЅРёРµ id={message_id} РЅРµ РЅР°Р№РґРµРЅРѕ")
                        return False

                    import json
                    existing_metadata = json.loads(row[0]) if row[0] else {}

                    # РРЎРџР РђР’Р›Р•РќРћ (2026-03-05): РЎРѕС…СЂР°РЅСЏРµРј api_info Рё client_system РїСЂРё РѕР±РЅРѕРІР»РµРЅРёРё metadata
                    # Р•СЃР»Рё РЅРѕРІС‹Рµ РјРµС‚Р°РґР°РЅРЅС‹Рµ РЅРµ СЃРѕРґРµСЂР¶Р°С‚ СЌС‚Рё РїРѕР»СЏ, СЃРѕС…СЂР°РЅСЏРµРј РёС… РёР· СЃСѓС‰РµСЃС‚РІСѓСЋС‰РёС…
                    preserved_fields = ['api_info', 'client_system']
                    for field in preserved_fields:
                        if field in existing_metadata and field not in metadata:
                            metadata[field] = existing_metadata[field]
                            logger.info(f"[DEBUG] РЎРѕС…СЂР°РЅРµРЅ {field} РїСЂРё РѕР±РЅРѕРІР»РµРЅРёРё metadata")

                    # РћР±СЉРµРґРёРЅСЏРµРј РјРµС‚Р°РґР°РЅРЅС‹Рµ
                    existing_metadata.update(metadata)

                    # РћР±РЅРѕРІР»СЏРµРј РІ Р‘Р”
                    cursor.execute("""
                        UPDATE dialog_logs
                        SET metadata = %s
                        WHERE id = %s
                    """, [json.dumps(existing_metadata, ensure_ascii=False), message_id])

                    logger.debug(f"Metadata РѕР±РЅРѕРІР»РµРЅР° РґР»СЏ СЃРѕРѕР±С‰РµРЅРёСЏ id={message_id}")
                    return True

            result = await sync_to_async(update_sync)()
            return result

        except Exception as e:
            logger.error(f"РћС€РёР±РєР° РѕР±РЅРѕРІР»РµРЅРёСЏ metadata РґР»СЏ СЃРѕРѕР±С‰РµРЅРёСЏ {message_id}: {e}")
            return False

    async def _get_dialog_history(self, session_id: str, limit: int = 10) -> list:
        """
        РџРѕР»СѓС‡РёС‚СЊ РёСЃС‚РѕСЂРёСЋ РґРёР°Р»РѕРіР° РёР· Р‘Р”

        РРЎРџР РђР’Р›Р•РќРћ (2026-01-05): РСЃРїРѕР»СЊР·СѓРµС‚ raw SQL РІРјРµСЃС‚Рѕ ORM
        ORM РєРµС€ РЅРµ РѕР±РЅРѕРІР»СЏРµС‚СЃСЏ РїРѕСЃР»Рµ raw SQL INSERT РІ DialogLoggerService!

        Args:
            session_id: ID СЃРµСЃСЃРёРё
            limit: РњР°РєСЃРёРјР°Р»СЊРЅРѕРµ РєРѕР»РёС‡РµСЃС‚РІРѕ СЃРѕРѕР±С‰РµРЅРёР№

        Returns:
            list: РСЃС‚РѕСЂРёСЏ РІ С„РѕСЂРјР°С‚Рµ РґР»СЏ MainAgent
                [
                    {'role': 'user', 'text': '...', 'timestamp': '...'},
                    {'role': 'bot', 'text': '...', 'timestamp': '...'}
                ]
        """
        try:
            from django.db import connection

            def get_history_sync():
                with connection.cursor() as cursor:
                    # РРЎРџР РђР’Р›Р•РќРћ (2026-01-05): Р”РѕР±Р°РІР»СЏРµРј metadata РІ SELECT РґР»СЏ txtPrb
                    cursor.execute("""
                        SELECT direction, message_content, timestamp, metadata
                        FROM dialog_logs
                        WHERE session_id = %s
                        ORDER BY timestamp DESC
                        LIMIT %s
                    """, [session_id, limit])

                    messages = []
                    for row in cursor.fetchall():
                        # РџР°СЂСЃРёРј metadata РµСЃР»Рё СЌС‚Рѕ СЃС‚СЂРѕРєР°
                        metadata = row[3]
                        if isinstance(metadata, str):
                            try:
                                import json
                                metadata = json.loads(metadata)
                            except:
                                metadata = {}

                        messages.append({
                            'role': 'user' if row[0] == 'inbound' else 'bot',
                            'text': row[1],
                            'timestamp': row[2].isoformat(),
                            'metadata': metadata if isinstance(metadata, dict) else {}
                        })

                    # Р Р°Р·РІРѕСЂР°С‡РёРІР°РµРј СЃРїРёСЃРѕРє (СЃРЅР°С‡Р°Р»Р° СЃС‚Р°СЂС‹Рµ СЃРѕРѕР±С‰РµРЅРёСЏ)
                    return list(reversed(messages))

            return await sync_to_async(get_history_sync)()

        except Exception as e:
            logger.error(f"MessageHandler: РћС€РёР±РєР° РїРѕР»СѓС‡РµРЅРёСЏ РёСЃС‚РѕСЂРёРё: {e}")
            return []

    def _extract_bot_response(self, result: Dict) -> str:
        """
        РР·РІР»РµС‡СЊ С‚РµРєСЃС‚ РѕС‚РІРµС‚Р° Р±РѕС‚Р° РёР· СЂРµР·СѓР»СЊС‚Р°С‚Р° MainAgent

        РРЎРџР РђР’Р›Р•РќРћ (2025-12-25): Р”РѕР±Р°РІР»РµРЅР° РѕР±СЂР°Р±РѕС‚РєР° СЃС‚Р°С‚СѓСЃРѕРІ CONFIRMED Рё REJECTED

        Args:
            result: Р РµР·СѓР»СЊС‚Р°С‚ РѕС‚ MainAgent

        Returns:
            str: РўРµРєСЃС‚ РѕС‚РІРµС‚Р° РґР»СЏ РѕС‚РїСЂР°РІРєРё РїРѕР»СЊР·РѕРІР°С‚РµР»СЋ
        """
        if not result:
            return "РџСЂРѕРёР·РѕС€Р»Р° РѕС€РёР±РєР° РѕР±СЂР°Р±РѕС‚РєРё"

        status = result.get('status')

        if status == 'ADDRESS_REQUIRED':
            return result.get('message') or "РќР°РїРёС€РёС‚Рµ, РїРѕР¶Р°Р»СѓР№СЃС‚Р°, Р°РґСЂРµСЃ: СѓР»РёС†Сѓ Рё РЅРѕРјРµСЂ РґРѕРјР°."

        elif status == 'ADDRESS_NOT_SERVICED':
            return result.get('message') or "РђРґСЂРµСЃ РЅР°Р№РґРµРЅ, РЅРѕ РїРѕРєР° РЅРµ РїСЂРёРІСЏР·Р°РЅ Рє РѕР±СЃР»СѓР¶РёРІР°РµРјРѕРјСѓ РѕР±СЉРµРєС‚Сѓ."

        elif status == 'ADDRESS_ACCEPTED':
            return result.get('message') or "РђРґСЂРµСЃ РЅР°С€Р»Р°. Р§С‚Рѕ СЃР»СѓС‡РёР»РѕСЃСЊ?"

        elif status == 'SUCCESS':
            # РЈСЃР»СѓРіР° РѕРїСЂРµРґРµР»РµРЅР° РѕРґРЅРѕР·РЅР°С‡РЅРѕ
            service_name = result.get('service_name', 'СѓСЃР»СѓРіР°')
            message = result.get('message')

            # РРЎРџР РђР’Р›Р•РќРћ (2026-03-04): РџСЂРѕРІРµСЂРєР° РЅР° СЃС‚СЂРѕРєСѓ "null"
            if message and message != "null":
                return message
            # РРЎРџР РђР’Р›Р•РќРР• (2026-01-12): РџРѕ РїСЂР°РІРёР»Сѓ 7 CLAUDE.md - С‚РѕР»СЊРєРѕ РѕС‚РєСЂС‹С‚С‹Рµ РІРѕРїСЂРѕСЃС‹!
            # Р—РђРџР Р•Р©Р•РќРћ: "Р­С‚Рѕ РїСЂР°РІРёР»СЊРЅРѕ?" - Р·Р°РєСЂС‹С‚С‹Р№ РІРѕРїСЂРѕСЃ
            return f"РџРѕРЅСЏР»Р° РІР°СЃ: {service_name}. РћРїРёС€РёС‚Рµ РїРѕРґСЂРѕР±РЅРµРµ РґРµС‚Р°Р»Рё, РµСЃР»Рё РЅСѓР¶РЅРѕ."

        elif status == 'CONFIRMED':
            # РРЎРџР РђР’Р›Р•РќРћ (2025-12-25): РџРѕР»СЊР·РѕРІР°С‚РµР»СЊ РїРѕРґС‚РІРµСЂРґРёР» СѓСЃР»СѓРіСѓ
            message = result.get('message')
            # РРЎРџР РђР’Р›Р•РќРћ (2026-03-04): РџСЂРѕРІРµСЂРєР° РЅР° СЃС‚СЂРѕРєСѓ "null"
            if message and message != "null":
                return message

            service_name = result.get('service_name', 'СѓСЃР»СѓРіР°')
            return f"РЎРїР°СЃРёР±Рѕ Р·Р° РїРѕРґС‚РІРµСЂР¶РґРµРЅРёРµ. Р—Р°СЏРІРєР° СЃРѕР·РґР°РЅР° РЅР° СѓСЃР»СѓРіСѓ: {service_name}"

        elif status == 'REJECTED':
            # РРЎРџР РђР’Р›Р•РќРћ (2025-12-25): РџРѕР»СЊР·РѕРІР°С‚РµР»СЊ РѕС‚СЂРёС†Р°Р»
            message = result.get('message')
            # РРЎРџР РђР’Р›Р•РќРћ (2026-03-04): РџСЂРѕРІРµСЂРєР° РЅР° СЃС‚СЂРѕРєСѓ "null"
            if message and message != "null":
                return message
            return "РџРѕРЅСЏР», СѓС‚РѕС‡РЅРёС‚Рµ РїРѕР¶Р°Р»СѓР№СЃС‚Р° С‡С‚Рѕ РёРјРµРЅРЅРѕ Сѓ РІР°СЃ РїСЂРѕР±Р»РµРјР°?"

        elif status == 'AMBIGUOUS':
            # РќСѓР¶РµРЅ СѓС‚РѕС‡РЅСЏСЋС‰РёР№ РІРѕРїСЂРѕСЃ
            message = result.get('message')

            # РРЎРџР РђР’Р›Р•РќРћ (2026-03-04): РџСЂРѕРІРµСЂРєР° РЅР° СЃС‚СЂРѕРєСѓ "null" (JSON null РїСЂРё С‡С‚РµРЅРёРё РёР· Р‘Р”)
            # PostgreSQL JSONB ->> operator РІРѕР·РІСЂР°С‰Р°РµС‚ "null" РєР°Рє СЃС‚СЂРѕРєСѓ РґР»СЏ JSON null
            if message and message != "null":
                return message

            # Р•СЃР»Рё РЅРµС‚ message РёР»Рё message == "null", РёСЃРїРѕР»СЊР·СѓРµРј СЃРїРёСЃРѕРє РєР°РЅРґРёРґР°С‚РѕРІ
            candidates = result.get('candidates', [])
            if candidates:
                # РРЎРџР РђР’Р›Р•РќРР• (2026-01-12): РџРѕ РїСЂР°РІРёР»Сѓ 7 CLAUDE.md - С‚РѕР»СЊРєРѕ РѕС‚РєСЂС‹С‚С‹Рµ РІРѕРїСЂРѕСЃС‹!
                # Р—РђРџР Р•Р©Р•РќРћ: "СЌС‚Рѕ X, Y, Z?" - РїРµСЂРµС‡РёСЃР»РµРЅРёРµ + Р·Р°РєСЂС‹С‚С‹Р№ РІРѕРїСЂРѕСЃ
                # РџР РђР’РР›Р¬РќРћ: РѕС‚РєСЂС‹С‚С‹Р№ РІРѕРїСЂРѕСЃ Р±РµР· РїРµСЂРµС‡РёСЃР»РµРЅРёСЏ
                # РРЎРџР РђР’Р›Р•РќРР• (2026-02-14): Fallback РІРѕРїСЂРѕСЃ Р·Р°РєРѕРјРјРµРЅС‚РёСЂРѕРІР°РЅ
                # return "РћРїРёС€РёС‚Рµ РїРѕРґСЂРѕР±РЅРµРµ, С‡С‚Рѕ РёРјРµРЅРЅРѕ РїСЂРѕРёР·РѕС€Р»Рѕ?"
                pass  # MainAgent СЃР°Рј РґРѕР»Р¶РµРЅ СЃРіРµРЅРµСЂРёСЂРѕРІР°С‚СЊ РІРѕРїСЂРѕСЃ

            return "РџРѕР¶Р°Р»СѓР№СЃС‚Р°, СѓС‚РѕС‡РЅРёС‚Рµ РґРµС‚Р°Р»Рё РїСЂРѕР±Р»РµРјС‹."

        elif status == 'ERROR':
            error = result.get('error', 'РќРµРёР·РІРµСЃС‚РЅР°СЏ РѕС€РёР±РєР°')
            return f"РџСЂРѕРёР·РѕС€Р»Р° РѕС€РёР±РєР°: {error}"

        else:
            # Fallback - РРЎРџР РђР’Р›Р•РќРћ (2025-12-25): РЈР±СЂР°РЅС‹ С„СЂР°Р·С‹ РїСЂРѕ "Р±РѕС‚" Рё "РїРѕРїСЂРѕР±СѓСЋ РѕРїСЂРµРґРµР»РёС‚СЊ"
            return "РћРїРёС€РёС‚Рµ, РїРѕР¶Р°Р»СѓР№СЃС‚Р°: С‡С‚Рѕ РёРјРµРЅРЅРѕ СЃР»СѓС‡РёР»РѕСЃСЊ? Р§С‚Рѕ СЃР»РѕРјР°Р»РѕСЃСЊ, С‚РµС‡РµС‚ РёР»Рё РЅРµ СЂР°Р±РѕС‚Р°РµС‚?"

    async def _check_confirmation_response(
        self,
        text: str,
        original_text: str,
        dialog_history: list,
        session_id: str,
        channel: str,
        user_id: str,
        django_user_id: Optional[int],
        message_log_id: Optional[int],
        source_metadata: Optional[Dict] = None,
    ) -> Dict:
        """
        РџСЂРѕРІРµСЂСЏРµС‚, СЏРІР»СЏРµС‚СЃСЏ Р»Рё СЃРѕРѕР±С‰РµРЅРёРµ РѕС‚РІРµС‚РѕРј РЅР° РїРѕРґС‚РІРµСЂР¶РґРµРЅРёРµ

        РРЎРџР РђР’Р›Р•РќРћ (2025-12-25): Р”РѕР±Р°РІР»РµРЅР° РѕР±СЂР°Р±РѕС‚РєР° "РґР°"/"РЅРµС‚" РЅР° РїРѕРґС‚РІРµСЂР¶РґРµРЅРёСЏ

        Args:
            text: РћС‡РёС‰РµРЅРЅС‹Р№ С‚РµРєСЃС‚ СЃРѕРѕР±С‰РµРЅРёСЏ
            original_text: РћСЂРёРіРёРЅР°Р»СЊРЅС‹Р№ С‚РµРєСЃС‚
            dialog_history: РСЃС‚РѕСЂРёСЏ РґРёР°Р»РѕРіР°
            session_id: ID СЃРµСЃСЃРёРё

        Returns:
            Dict: {
                'is_confirmation_response': bool,
                'result': dict  # Р РµР·СѓР»СЊС‚Р°С‚ РѕР±СЂР°Р±РѕС‚РєРё (РµСЃР»Рё СЌС‚Рѕ РѕС‚РІРµС‚ РЅР° РїРѕРґС‚РІРµСЂР¶РґРµРЅРёРµ)
            }
        """
        try:
            # РС‰РµРј РїРѕСЃР»РµРґРЅРµРµ СЃРѕРѕР±С‰РµРЅРёРµ Р±РѕС‚Р°
            bot_messages = [m for m in dialog_history if m.get('role') == 'bot']

            if not bot_messages:
                return {'is_confirmation_response': False}

            last_bot_msg = bot_messages[-1]
            last_bot_text = last_bot_msg.get('text', '')

            # РРЎРџР РђР’Р›Р•РќРР• (2026-01-12): РџСЂРѕРІРµСЂСЏРµРј РѕС‚РєСЂС‹С‚С‹Рµ РІРѕРїСЂРѕСЃС‹ ("РџРѕС…РѕР¶Рµ РЅР° РїСЂРѕР±Р»РµРјСѓ", "РћРїРёС€РёС‚Рµ РїРѕРґСЂРѕР±РЅРµРµ")
            # РЎС‚Р°СЂС‹Рµ Р·Р°РєСЂС‹С‚С‹Рµ РІРѕРїСЂРѕСЃС‹ Р±РѕР»СЊС€Рµ РЅРµ РёСЃРїРѕР»СЊР·СѓСЋС‚СЃСЏ РїРѕ РїСЂР°РІРёР»Сѓ 7 CLAUDE.md
            has_clarification_question = (
                'РїРѕС…РѕР¶Рµ РЅР°' in last_bot_text.lower() or
                'РѕРїРёС€РёС‚Рµ РїРѕРґСЂРѕР±РЅРµРµ' in last_bot_text.lower() or
                'СѓС‚РѕС‡РЅРёС‚Рµ РґРµС‚Р°Р»Рё' in last_bot_text.lower() or
                # Р”Р»СЏ РѕР±СЂР°С‚РЅРѕР№ СЃРѕРІРјРµСЃС‚РёРјРѕСЃС‚Рё СЃРѕ СЃС‚Р°СЂС‹РјРё РґРёР°Р»РѕРіР°РјРё
                'РїСЂР°РІРёР»СЊРЅРѕ Р»Рё СЏ РїРѕРЅСЏР»' in last_bot_text.lower()
            )

            if not has_clarification_question:
                return {'is_confirmation_response': False}

            # Р­С‚Рѕ РѕС‚РІРµС‚ РЅР° СѓС‚РѕС‡РЅСЏСЋС‰РёР№ РІРѕРїСЂРѕСЃ - РїСЂРѕРІРµСЂСЏРµРј С‡С‚Рѕ РѕС‚РІРµС‚РёР» РїРѕР»СЊР·РѕРІР°С‚РµР»СЊ
            text_lower = text.lower().strip()

            # РРЎРџР РђР’Р›Р•РќРР• (2026-01-12): РћР±СЂР°Р±РѕС‚РєР° РЅРµРѕРїСЂРµРґРµР»РµРЅРЅС‹С… РѕС‚РІРµС‚РѕРІ
            # "РЅРµ Р·РЅР°СЋ", "РІРѕР·РјРѕР¶РЅРѕ", "РЅРµ СѓРІРµСЂРµРЅ" - РїРµСЂРµРґР°РµРј РІ MainAgent РґР»СЏ РґРѕРїРѕР»РЅРёС‚РµР»СЊРЅРѕРіРѕ Р°РЅР°Р»РёР·Р°
            uncertain_responses = ['РЅРµ Р·РЅР°СЋ', 'РЅРµ СѓРІРµСЂРµРЅ', 'РІРѕР·РјРѕР¶РЅРѕ', 'С…Р·', 'РјРѕР¶РµС‚ Р±С‹С‚СЊ', 'С‚РѕС‡РЅРѕ РЅРµ Р·РЅР°СЋ']
            if any(resp in text_lower for resp in uncertain_responses):
                logger.info(f"MessageHandler: РќРµРѕРїСЂРµРґРµР»РµРЅРЅС‹Р№ РѕС‚РІРµС‚: '{text}' - РїРµСЂРµРґР°РµРј РІ MainAgent")
                # РќР• РїРѕРјРµС‡Р°РµРј РєР°Рє confirmation_response, РґР°РµРј MainAgent РѕР±СЂР°Р±РѕС‚Р°С‚СЊ
                return {'is_confirmation_response': False, 'is_uncertain': True}

            # РџРћР”РўР’Р•Р Р–Р”Р•РќРР• (РїРѕР»СЊР·РѕРІР°С‚РµР»СЊ СЏРІРЅРѕ РїРѕРґС‚РІРµСЂР¶РґР°РµС‚)
            if text_lower in ['РґР°', 'РІРµСЂРЅРѕ', 'РїСЂР°РІРёР»СЊРЅРѕ', 'С‚Рѕ СЃР°РјРѕРµ', 'Р°РіР°', 'yes', 'РїРѕРґС‚РІРµСЂР¶РґР°СЋ']:
                logger.info(f"MessageHandler: РћР±РЅР°СЂСѓР¶РµРЅРѕ РїРѕРґС‚РІРµСЂР¶РґРµРЅРёРµ '{text}'")

                # РРЎРџР РђР’Р›Р•РќРћ (2025-12-25): РџСЂРѕР±СѓРµРј РёР·РІР»РµС‡СЊ service_result РёР· СЂР°Р·РЅС‹С… РёСЃС‚РѕС‡РЅРёРєРѕРІ
                service_result = await self._get_last_service_result(session_id)
                last_bot_metadata = self._get_last_bot_metadata_from_history(dialog_history)

                # Fallback: РµСЃР»Рё РІ Р‘Р” РЅРµС‚, РїСЂРѕР±СѓРµРј РёР·РІР»РµС‡СЊ РёР· РёСЃС‚РѕСЂРёРё РґРёР°Р»РѕРіР° (РґР»СЏ С‚РµСЃС‚РѕРІ)
                if not service_result:
                    service_result = await self._extract_service_result_from_history(dialog_history)

                if service_result and service_result.get('status') == 'SUCCESS':
                    intake_context = last_bot_metadata.get('intake_context') if isinstance(last_bot_metadata, dict) else {}
                    if not isinstance(intake_context, dict):
                        intake_context = {}
                    address_components = intake_context.get('address_components') or last_bot_metadata.get('address_components') or {}
                    address_validation = intake_context.get('address_validation') or last_bot_metadata.get('address_validation') or {}
                    service_result = self._merge_result_metadata(
                        service_result,
                        address_components=address_components,
                        address_validation=address_validation,
                        intake_context=intake_context,
                    )

                    service_id = service_result.get('service_id')
                    service_name = service_result.get('service_name')

                    logger.info(f"MessageHandler: РџРѕРґС‚РІРµСЂР¶РґРµРЅР° СѓСЃР»СѓРіР° ID:{service_id} | {service_name}")

                    intake_result = None
                    if self.chat_intake_service:
                        intake_result = await sync_to_async(self.chat_intake_service.create_from_chat)(
                            service_result=service_result,
                            intake_context=intake_context,
                            original_text=original_text,
                            channel=channel,
                            session_id=session_id,
                            user_id=user_id,
                            django_user_id=django_user_id,
                            message_log_id=message_log_id,
                            source_metadata=source_metadata or {},
                        )

                    if intake_result and intake_result.get('created'):
                        work_order_no = intake_result.get('work_order_no')
                        message = (
                            f"Р“РѕС‚РѕРІРѕ. РЎРѕР·РґР°Р»Р° Р·Р°СЏРІРєСѓ {work_order_no}."
                            if work_order_no else
                            f"Р“РѕС‚РѕРІРѕ. РЎРѕР·РґР°Р»Р° Р·Р°СЏРІРєСѓ РїРѕ СѓСЃР»СѓРіРµ: {service_name}."
                        )
                        result = {
                            'status': 'CONFIRMED',
                            'service_id': service_id,
                            'service_name': service_name,
                            'message': message,
                            'confirmed': True,
                            'work_order_id': intake_result.get('work_order_id'),
                            'work_order_no': work_order_no,
                            '_metadata': {
                                'intake_context': intake_context,
                                'chat_intake_result': intake_result,
                            },
                        }
                    else:
                        failure_message = (
                            intake_result.get('message')
                            if isinstance(intake_result, dict) and intake_result.get('message')
                            else f"РЎРїР°СЃРёР±Рѕ. РџРѕРґС‚РІРµСЂР¶РґРµРЅРёРµ РїРѕР»СѓС‡РёР»Р°, РЅРѕ Р·Р°СЏРІРєСѓ РїРѕ СѓСЃР»СѓРіРµ '{service_name}' СЃРѕР·РґР°С‚СЊ РЅРµ СѓРґР°Р»РѕСЃСЊ."
                        )
                        result = {
                            'status': 'ERROR',
                            'service_id': service_id,
                            'service_name': service_name,
                            'error': failure_message,
                            'message': failure_message,
                            '_metadata': {
                                'intake_context': intake_context,
                                'chat_intake_result': intake_result,
                            },
                        }

                    return {
                        'is_confirmation_response': True,
                        'result': result
                    }
                else:
                    logger.warning("MessageHandler: РќРµ СѓРґР°Р»РѕСЃСЊ РёР·РІР»РµС‡СЊ service_result РґР»СЏ РїРѕРґС‚РІРµСЂР¶РґРµРЅРёСЏ")
                    return {'is_confirmation_response': False}

            # РћРўР РР¦РђРќРР• (РїРѕР»СЊР·РѕРІР°С‚РµР»СЊ СЏРІРЅРѕ РѕС‚СЂРёС†Р°РµС‚)
            elif text_lower in ['РЅРµС‚', 'РЅРµРїСЂР°РІРёР»СЊРЅРѕ', 'РЅРµ С‚Рѕ', 'РЅРµС‚ РЅРµ С‚Рѕ', 'no', 'РЅРµРІРµСЂРЅРѕ']:
                logger.info(f"MessageHandler: РћР±РЅР°СЂСѓР¶РµРЅРѕ РѕС‚СЂРёС†Р°РЅРёРµ '{text}'")

                result = {
                    'status': 'REJECTED',
                    'message': "РџРѕРЅСЏР». РћРїРёС€РёС‚Рµ РІР°С€Сѓ РїСЂРѕР±Р»РµРјСѓ РїРѕРґСЂРѕР±РЅРµРµ, С‡С‚РѕР±С‹ СЏ РјРѕРі РїСЂР°РІРёР»СЊРЅРѕ РїРѕРјРѕС‡СЊ."
                }

                return {
                    'is_confirmation_response': True,
                    'result': result
                }

            # Р”СЂСѓРіРѕР№ РѕС‚РІРµС‚ - РїРµСЂРµРґР°РµРј РІ MainAgent РєР°Рє РѕР±С‹С‡РЅРѕРµ СЃРѕРѕР±С‰РµРЅРёРµ
            else:
                logger.info(f"MessageHandler: РћС‚РІРµС‚ РЅР° СѓС‚РѕС‡РЅРµРЅРёРµ: '{text}' - РїРµСЂРµРґР°РµРј РІ MainAgent")
                return {'is_confirmation_response': False}

        except Exception as e:
            logger.error(f"MessageHandler: РћС€РёР±РєР° РїСЂРѕРІРµСЂРєРё РѕС‚РІРµС‚Р° РЅР° РїРѕРґС‚РІРµСЂР¶РґРµРЅРёРµ: {e}")
            return {'is_confirmation_response': False}

    def _get_last_bot_metadata_from_history(self, dialog_history: list) -> Dict:
        return get_last_bot_metadata_from_history(dialog_history)

    def _build_intake_context(
        self,
        *,
        existing_context: Optional[Dict],
        address_components: Dict,
        address_validation: Dict,
    ) -> Dict:
        return build_intake_context(
            existing_context=existing_context,
            address_components=address_components,
            address_validation=address_validation,
        )

    def _merge_result_metadata(
        self,
        result: Dict,
        *,
        address_components: Optional[Dict] = None,
        address_validation: Optional[Dict] = None,
        intake_context: Optional[Dict] = None,
    ) -> Dict:
        return merge_result_metadata(
            result,
            address_components=address_components,
            address_validation=address_validation,
            intake_context=intake_context,
        )

    def _message_is_address_only(self, text: str, address_components: Dict) -> bool:
        return message_is_address_only(text, address_components)

    def _format_address(self, address_components: Dict) -> str:
        return format_address(address_components)

    async def _get_last_service_result(self, session_id: str) -> Optional[Dict]:
        """
        РР·РІР»РµРєР°РµС‚ service_result РёР· РїРѕСЃР»РµРґРЅРµРіРѕ СЃРѕРѕР±С‰РµРЅРёСЏ Р±РѕС‚Р°

        Args:
            session_id: ID СЃРµСЃСЃРёРё

        Returns:
            Dict: service_result РёР»Рё None
        """
        try:
            from message_handler.models import MessageLog

            def get_last_bot_msg_sync():
                # РС‰РµРј РїРѕСЃР»РµРґРЅРµРµ РёСЃС…РѕРґСЏС‰РµРµ СЃРѕРѕР±С‰РµРЅРёРµ СЃ metadata
                msg = MessageLog.objects.filter(
                    session_id=session_id,
                    direction='outbound'
                ).exclude(
                    metadata={}
                ).order_by('-timestamp').first()  # РРЎРџР РђР’Р›Р•РќРћ: Р±С‹Р»Рѕ created_at

                if msg and msg.metadata:
                    return msg.metadata.get('service_result')

            return await sync_to_async(get_last_bot_msg_sync)()

        except Exception as e:
            logger.error(f"MessageHandler: РћС€РёР±РєР° РїРѕР»СѓС‡РµРЅРёСЏ service_result: {e}")
            return None

    async def _extract_service_result_from_history(self, dialog_history: list) -> Optional[Dict]:
        """
        РР·РІР»РµРєР°РµС‚ service_result РёР· РёСЃС‚РѕСЂРёРё РґРёР°Р»РѕРіР° (fallback РґР»СЏ С‚РµСЃС‚РѕРІ)

        РРЎРџР РђР’Р›Р•РќРћ (2025-12-25): Р”РѕР±Р°РІР»РµРЅРѕ РґР»СЏ СЂР°Р±РѕС‚С‹ Р±РµР· Р‘Р” РІ С‚РµСЃС‚Р°С…
        РРЎРџР РђР’Р›Р•РќРћ (2026-01-12): РћР±РЅРѕРІР»РµРЅРѕ РґР»СЏ РѕС‚РєСЂС‹С‚С‹С… РІРѕРїСЂРѕСЃРѕРІ

        Args:
            dialog_history: РСЃС‚РѕСЂРёСЏ РґРёР°Р»РѕРіР°

        Returns:
            Dict: Mock service_result РёР»Рё None
        """
        try:
            # РРЎРџР РђР’Р›Р•РќРР• (2026-01-12): РџСЂРѕРІРµСЂСЏРµРј РѕС‚РєСЂС‹С‚С‹Рµ РІРѕРїСЂРѕСЃС‹ ("РџРѕС…РѕР¶Рµ РЅР° РїСЂРѕР±Р»РµРјСѓ: ...")
            for msg in reversed(dialog_history):
                if msg.get('role') == 'bot':
                    text = msg.get('text', '')
                    # РС‰РµРј РЅР°Р·РІР°РЅРёРµ СѓСЃР»СѓРіРё РїРѕСЃР»Рµ "РџРѕС…РѕР¶Рµ РЅР° РїСЂРѕР±Р»РµРјСѓ:" РёР»Рё "РџСЂР°РІРёР»СЊРЅРѕ Р»Рё СЏ РїРѕРЅСЏР», С‡С‚Рѕ Сѓ РІР°СЃ:"
                    import re
                    # РќРѕРІС‹Р№ С„РѕСЂРјР°С‚: "РџРѕС…РѕР¶Рµ РЅР° РїСЂРѕР±Р»РµРјСѓ: X. РћРїРёС€РёС‚Рµ РїРѕРґСЂРѕР±РЅРµРµ..."
                    match_new = re.search(r'РџРѕС…РѕР¶Рµ РЅР° РїСЂРѕР±Р»РµРјСѓ[:\s]+([^.]+)', text, re.IGNORECASE)
                    # РЎС‚Р°СЂС‹Р№ С„РѕСЂРјР°С‚ (РґР»СЏ РѕР±СЂР°С‚РЅРѕР№ СЃРѕРІРјРµСЃС‚РёРјРѕСЃС‚Рё): "РџСЂР°РІРёР»СЊРЅРѕ Р»Рё СЏ РїРѕРЅСЏР», С‡С‚Рѕ Сѓ РІР°СЃ: X?"
                    match_old = re.search(r'С‡С‚Рѕ Сѓ РІР°СЃ[:\s]+([^.]+)', text, re.IGNORECASE)

                    service_name = None
                    if match_new:
                        service_name = match_new.group(1).strip()
                    elif match_old:
                        service_name = match_old.group(1).strip()

                    if service_name:
                        # Mock service_result
                        return {
                            'status': 'SUCCESS',
                            'service_id': 25,  # Mock ID
                            'service_name': service_name,
                            'confidence': 0.8
                        }

            return None

        except Exception as e:
            logger.error(f"MessageHandler: РћС€РёР±РєР° РёР·РІР»РµС‡РµРЅРёСЏ service_result РёР· РёСЃС‚РѕСЂРёРё: {e}")
            return None

    async def get_session_messages(self, session_id: str, limit: int = 50) -> list:
        """
        РџРѕР»СѓС‡РёС‚СЊ РІСЃРµ СЃРѕРѕР±С‰РµРЅРёСЏ СЃРµСЃСЃРёРё (РґР»СЏ Р°РґРјРёРЅРєРё/РѕС‚Р»Р°РґРєРё)

        Args:
            session_id: ID СЃРµСЃСЃРёРё
            limit: РњР°РєСЃРёРјР°Р»СЊРЅРѕРµ РєРѕР»РёС‡РµСЃС‚РІРѕ СЃРѕРѕР±С‰РµРЅРёР№

        Returns:
            list: РЎРѕРѕР±С‰РµРЅРёСЏ СЃ РјРµС‚Р°РґР°РЅРЅС‹РјРё
        """
        try:
            from message_handler.models import MessageLog

            def get_messages_sync():
                messages = MessageLog.objects.filter(
                    session_id=session_id
                ).order_by('timestamp')[:limit]  # РРЎРџР РђР’Р›Р•РќРћ: Р±С‹Р»Рѕ created_at

                return [
                    {
                        'id': msg.id,
                        'channel': msg.get_channel_display(),
                        'direction': msg.get_direction_display(),
                        'text': msg.message_content,  # РРЎРџР РђР’Р›Р•РќРћ: Р±С‹Р»Рѕ msg.text
                        'timestamp': msg.timestamp.isoformat(),  # РРЎРџР РђР’Р›Р•РќРћ: Р±С‹Р»Рѕ msg.created_at
                        'metadata': msg.metadata
                    }
                    for msg in messages
                ]

            return await sync_to_async(get_messages_sync)()

        except Exception as e:
            logger.error(f"MessageHandler: РћС€РёР±РєР° РїРѕР»СѓС‡РµРЅРёСЏ СЃРѕРѕР±С‰РµРЅРёР№ СЃРµСЃСЃРёРё: {e}")
            return []

    async def log_outbound_message(
        self,
        text: str,
        user_id: str,
        channel: str,
        session_id: str,
        metadata: Dict = None
    ) -> Dict:
        """
        РџСѓР±Р»РёС‡РЅС‹Р№ РјРµС‚РѕРґ РґР»СЏ Р»РѕРіРёСЂРѕРІР°РЅРёСЏ РёСЃС…РѕРґСЏС‰РёС… СЃРѕРѕР±С‰РµРЅРёР№ (Bot -> User)

        РСЃРїРѕР»СЊР·СѓРµС‚СЃСЏ Р±РѕС‚Р°РјРё (Telegram, WhatsApp) РґР»СЏ Р»РѕРіРёСЂРѕРІР°РЅРёСЏ РѕС‚РІРµС‚РѕРІ РїРѕР»СЊР·РѕРІР°С‚РµР»СЏРј.

        Args:
            text: РўРµРєСЃС‚ РёСЃС…РѕРґСЏС‰РµРіРѕ СЃРѕРѕР±С‰РµРЅРёСЏ
            user_id: ID РїРѕР»СЊР·РѕРІР°С‚РµР»СЏ РІ РєР°РЅР°Р»Рµ
            channel: РљР°РЅР°Р» СЃРІСЏР·Рё (telegram, whatsapp, web, etc)
            session_id: ID СЃРµСЃСЃРёРё РґРёР°Р»РѕРіР°
            metadata: Р”РѕРїРѕР»РЅРёС‚РµР»СЊРЅС‹Рµ РјРµС‚Р°РґР°РЅРЅС‹Рµ (txtPrb, filters, etc)

        Returns:
            Dict: Р РµР·СѓР»СЊС‚Р°С‚ Р»РѕРіРёСЂРѕРІР°РЅРёСЏ
        """
        try:
            # Р“РµРЅРµСЂРёСЂСѓРµРј message_id РґР»СЏ outbound
            import uuid
            message_id = str(uuid.uuid4())

            # Р›РѕРіРёСЂСѓРµРј С‡РµСЂРµР· РІРЅСѓС‚СЂРµРЅРЅРёР№ РјРµС‚РѕРґ
            result = await self._log_message(
                text=text,
                user_id=user_id,
                channel=channel,
                message_id=message_id,
                session_id=session_id,
                direction='outbound',
                metadata=metadata or {}
            )

            logger.info(f"вњ… Outbound СЃРѕРѕР±С‰РµРЅРёРµ Р·Р°РїРёСЃР°РЅРѕ: session_id={session_id}, text='{text[:50]}...'")
            return {'status': 'success', 'message_log_id': result.get('id')}

        except Exception as e:
            logger.error(f"вќЊ РћС€РёР±РєР° Р»РѕРіРёСЂРѕРІР°РЅРёСЏ outbound СЃРѕРѕР±С‰РµРЅРёСЏ: {e}")
            return {'status': 'error', 'error': str(e)}
