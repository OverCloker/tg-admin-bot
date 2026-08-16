import sqlite3
import re
from contextlib import suppress
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable
import json


DIG_GLOBAL_CHAT_ID = 0


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(frozen=True)
class AutoReply:
    chat_id: int
    username: str
    text: str
    media_type: str | None
    media_file_id: str | None
    updated_by: int | None
    updated_at: str


@dataclass(frozen=True)
class RegisteredChat:
    chat_id: int
    title: str
    type: str
    username: str | None
    updated_at: str


@dataclass(frozen=True)
class TriggerReply:
    chat_id: int
    trigger: str
    text: str
    media_type: str | None
    media_file_id: str | None
    updated_by: int | None
    updated_at: str
    aliases: tuple[str, ...] = ()


@dataclass(frozen=True)
class TriggerReplyVariant:
    id: int
    chat_id: int
    trigger: str
    variant_type: str
    text: str
    media_type: str | None
    media_file_id: str | None
    position: int
    updated_by: int | None
    updated_at: str
    aliases: tuple[str, ...] = ()


@dataclass(frozen=True)
class SeenUser:
    chat_id: int
    user_id: int
    username: str | None
    full_name: str
    is_bot: int
    updated_at: str


@dataclass(frozen=True)
class MiniAppProfileRole:
    user_id: int
    label: str
    emoji: str | None
    color: str | None
    granted_by: int | None
    updated_at: str


@dataclass(frozen=True)
class SocialGiftRecipient:
    user_id: int
    username: str | None
    full_name: str
    relation: str
    chat_count: int
    updated_at: str


@dataclass(frozen=True)
class ChatCouple:
    chat_id: int
    user1_id: int
    user2_id: int
    created_at: str


@dataclass(frozen=True)
class ParticipantActivity:
    chat_id: int
    user_id: int
    username: str | None
    full_name: str
    messages_count: int


@dataclass(frozen=True)
class ChatTopic:
    chat_id: int
    thread_id: int
    title: str
    updated_at: str


@dataclass(frozen=True)
class AuditLog:
    id: int
    chat_id: int | None
    actor_id: int | None
    actor_username: str | None
    actor_name: str
    source: str
    action: str
    details: str
    created_at: str


@dataclass(frozen=True)
class GiveawaySettings:
    chat_id: int
    trigger: str
    title: str
    winners_count: int
    updated_by: int | None
    updated_at: str


@dataclass(frozen=True)
class AlarmSettings:
    chat_id: int
    enabled: int
    permissions_json: str | None
    reactions_json: str | None
    alarm_text: str | None
    clear_text: str | None
    alarm_thread_id: int | None
    updated_by: int | None
    updated_at: str


@dataclass(frozen=True)
class GiveawayStat:
    chat_id: int
    user_id: int
    username: str | None
    full_name: str
    wins_count: int


@dataclass(frozen=True)
class StarPayment:
    id: int
    user_id: int
    username: str | None
    full_name: str
    chat_id: int | None
    amount: int
    currency: str
    charge_id: str
    created_at: str


@dataclass(frozen=True)
class PendingStarMessage:
    payload: str
    user_id: int
    chat_id: int
    text: str
    created_at: str


@dataclass(frozen=True)
class SecretMessageCompose:
    compose_id: str
    sender_id: int
    chat_id: int
    target_id: int
    target_name: str
    created_at: str


@dataclass(frozen=True)
class SecretMessage:
    message_id: str
    chat_id: int
    sender_id: int
    sender_username: str | None
    sender_name: str
    target_id: int
    target_name: str
    text: str
    created_at: str
    delivered_at: str | None


@dataclass(frozen=True)
class UserLoginRequest:
    login_id: str
    secret_hash: str
    user_id: int | None
    username: str | None
    full_name: str | None
    created_at: str
    expires_at: str
    approved_at: str | None
    consumed_at: str | None


@dataclass(frozen=True)
class UserSession:
    token_hash: str
    user_id: int
    username: str | None
    full_name: str
    created_at: str
    expires_at: str
    revoked_at: str | None


@dataclass(frozen=True)
class UserSubscription:
    user_id: int
    status: str
    expires_at: str | None
    telegram_payment_charge_id: str | None
    updated_at: str


@dataclass(frozen=True)
class AdminFeaturePermission:
    chat_id: int
    user_id: int
    feature: str
    allowed: int
    updated_by: int | None
    updated_at: str


@dataclass(frozen=True)
class Quote:
    id: int
    chat_id: int
    text: str
    author_name: str | None
    added_by: int | None
    created_at: str


@dataclass(frozen=True)
class Birthday:
    id: int
    chat_id: int
    day: int
    month: int
    text: str
    added_by: int | None
    created_at: str


@dataclass(frozen=True)
class Advertisement:
    id: int
    chat_id: int
    text: str
    enabled: int
    start_time: str
    interval_minutes: int
    duration_type: str
    start_mode: str
    scheduled_at: str | None
    topic_thread_id: int | None
    first_sent_at: str | None
    last_sent_at: str | None
    last_error: str | None
    created_by: int | None
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class AdvertisementAttachment:
    id: int
    advertisement_id: int
    media_type: str
    file_id: str
    filename: str
    position: int


@dataclass(frozen=True)
class AdvertisementSettings:
    chat_id: int
    enabled: int
    start_time: str
    interval_minutes: int
    next_ad_index: int
    last_sent_at: str | None
    updated_by: int | None
    updated_at: str


@dataclass(frozen=True)
class BlacklistWord:
    chat_id: int
    word: str
    added_by: int | None
    created_at: str


@dataclass(frozen=True)
class RollMuteSettings:
    chat_id: int
    mute_minutes: int
    cooldown_minutes: int
    updated_by: int | None
    updated_at: str
    last_used_at: str | None


@dataclass(frozen=True)
class RollMuteStat:
    chat_id: int
    user_id: int
    username: str | None
    full_name: str
    unlucky_count: int


@dataclass(frozen=True)
class QuietSettings:
    chat_id: int
    reply_text: str | None
    media_type: str | None
    media_file_id: str | None
    updated_by: int | None
    updated_at: str


@dataclass(frozen=True)
class QuietAdmin:
    chat_id: int
    user_id: int
    username: str | None
    full_name: str
    reason: str
    until_at: str
    created_by: int | None
    created_at: str


@dataclass(frozen=True)
class DigPlayer:
    chat_id: int
    user_id: int
    username: str | None
    full_name: str
    coins: int
    total_depth: int
    best_session_depth: int
    luck: int
    last_luck_at: str
    last_dig_at: str | None
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class DigItem:
    chat_id: int
    user_id: int
    item_key: str
    quantity: int
    updated_at: str


@dataclass(frozen=True)
class DigAchievement:
    chat_id: int
    user_id: int
    achievement_key: str
    created_at: str


class Database:
    def __init__(self, path: str) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.path, timeout=30, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("pragma journal_mode=WAL")
        self._conn.execute("pragma busy_timeout=30000")
        self._conn.execute("pragma synchronous=NORMAL")

    def close(self) -> None:
        self._conn.close()

    def init(self) -> None:
        self._conn.executescript(
            """
            create table if not exists chats (
                chat_id integer primary key,
                title text not null,
                type text not null,
                username text,
                updated_at text not null
            );

            create table if not exists auto_replies (
                chat_id integer not null,
                username text not null,
                text text not null,
                media_type text,
                media_file_id text,
                updated_by integer,
                updated_at text not null,
                primary key (chat_id, username),
                foreign key (chat_id) references chats(chat_id) on delete cascade
            );

            create table if not exists trigger_replies (
                chat_id integer not null,
                trigger text not null,
                text text not null,
                media_type text,
                media_file_id text,
                updated_by integer,
                updated_at text not null,
                primary key (chat_id, trigger),
                foreign key (chat_id) references chats(chat_id) on delete cascade
            );

            create table if not exists trigger_reply_variants (
                id integer primary key autoincrement,
                chat_id integer not null,
                trigger text not null,
                variant_type text not null,
                text text not null default '',
                media_type text,
                media_file_id text,
                position integer not null default 0,
                updated_by integer,
                updated_at text not null,
                foreign key (chat_id, trigger) references trigger_replies(chat_id, trigger) on delete cascade
            );
            create index if not exists idx_trigger_reply_variants_lookup
                on trigger_reply_variants(chat_id, trigger, position, id);

            create table if not exists trigger_aliases (
                chat_id integer not null,
                trigger text not null,
                alias text not null,
                updated_by integer,
                updated_at text not null,
                primary key (chat_id, trigger, alias),
                foreign key (chat_id, trigger) references trigger_replies(chat_id, trigger) on delete cascade
            );
            create index if not exists idx_trigger_aliases_lookup
                on trigger_aliases(chat_id, alias);

            create table if not exists seen_users (
                chat_id integer not null,
                user_id integer not null,
                username text,
                full_name text not null,
                is_bot integer not null default 0,
                updated_at text not null,
                primary key (chat_id, user_id),
                foreign key (chat_id) references chats(chat_id) on delete cascade
            );

            create table if not exists chat_friend_requests (
                chat_id integer not null,
                requester_id integer not null,
                target_id integer not null,
                created_at text not null,
                primary key (chat_id, requester_id, target_id),
                check (requester_id <> target_id),
                foreign key (chat_id) references chats(chat_id) on delete cascade
            );

            create table if not exists chat_friendships (
                chat_id integer not null,
                user1_id integer not null,
                user2_id integer not null,
                created_at text not null,
                primary key (chat_id, user1_id, user2_id),
                check (user1_id < user2_id),
                foreign key (chat_id) references chats(chat_id) on delete cascade
            );

            create index if not exists idx_chat_friendships_user1
                on chat_friendships(chat_id, user1_id);
            create index if not exists idx_chat_friendships_user2
                on chat_friendships(chat_id, user2_id);

            create table if not exists chat_couple_requests (
                chat_id integer not null,
                requester_id integer not null,
                target_id integer not null,
                created_at text not null,
                primary key (chat_id, requester_id, target_id),
                check (requester_id <> target_id),
                foreign key (chat_id) references chats(chat_id) on delete cascade
            );

            create table if not exists chat_couples (
                chat_id integer not null,
                user1_id integer not null,
                user2_id integer not null,
                created_at text not null,
                primary key (chat_id, user1_id, user2_id),
                check (user1_id < user2_id),
                foreign key (chat_id) references chats(chat_id) on delete cascade
            );

            create index if not exists idx_chat_couples_user1
                on chat_couples(chat_id, user1_id);
            create index if not exists idx_chat_couples_user2
                on chat_couples(chat_id, user2_id);

            create table if not exists participant_activity_daily (
                chat_id integer not null,
                user_id integer not null,
                activity_date text not null,
                messages_count integer not null default 0,
                updated_at text not null,
                primary key (chat_id, user_id, activity_date),
                foreign key (chat_id, user_id) references seen_users(chat_id, user_id) on delete cascade
            );

            create table if not exists daily_picks (
                chat_id integer not null,
                pick_key text not null,
                pick_date text not null,
                user_id integer not null,
                created_at text not null,
                primary key (chat_id, pick_key, pick_date),
                foreign key (chat_id) references chats(chat_id) on delete cascade
            );

            create table if not exists chat_topics (
                chat_id integer not null,
                thread_id integer not null,
                title text not null,
                updated_at text not null,
                primary key (chat_id, thread_id),
                foreign key (chat_id) references chats(chat_id) on delete cascade
            );

            create table if not exists audit_logs (
                id integer primary key autoincrement,
                chat_id integer,
                actor_id integer,
                actor_username text,
                actor_name text not null default '',
                source text not null,
                action text not null,
                details text not null default '',
                created_at text not null
            );

            create table if not exists device_events (
                id integer primary key autoincrement,
                app text not null,
                event_type text not null,
                event_name text not null,
                user_id integer,
                device_id text,
                app_version text,
                android_version text,
                sdk integer,
                manufacturer text,
                model text,
                screen text,
                density text,
                locale text,
                timezone text,
                network_type text,
                endpoint text,
                status_code integer,
                duration_ms integer,
                error_type text,
                message text,
                metadata_json text,
                created_at text not null
            );

            create index if not exists idx_device_events_created_at on device_events(created_at);
            create index if not exists idx_device_events_app_type on device_events(app, event_type);

            create table if not exists giveaway_settings (
                chat_id integer primary key,
                trigger text not null,
                title text not null,
                winners_count integer not null default 1,
                updated_by integer,
                updated_at text not null,
                foreign key (chat_id) references chats(chat_id) on delete cascade
            );

            create table if not exists giveaway_daily_picks (
                chat_id integer not null,
                pick_key text not null,
                pick_date text not null,
                pick_rank integer not null,
                user_id integer not null,
                created_at text not null,
                primary key (chat_id, pick_key, pick_date, pick_rank),
                foreign key (chat_id) references chats(chat_id) on delete cascade
            );

            create table if not exists alarm_settings (
                chat_id integer primary key,
                enabled integer not null default 0,
                permissions_json text,
                reactions_json text,
                alarm_text text,
                clear_text text,
                alarm_thread_id integer,
                updated_by integer,
                updated_at text not null,
                foreign key (chat_id) references chats(chat_id) on delete cascade
            );

            create table if not exists alarm_api_settings (
                chat_id integer primary key,
                enabled integer not null default 0,
                last_status text,
                last_notified_status text,
                last_alarm_message_id integer,
                last_clear_message_id integer,
                last_alarm_action_message_id integer,
                last_clear_action_message_id integer,
                updated_by integer,
                updated_at text not null,
                foreign key (chat_id) references chats(chat_id) on delete cascade
            );

            create table if not exists alarm_restriction_settings (
                chat_id integer primary key,
                enabled integer not null default 1,
                updated_by integer,
                updated_at text not null,
                foreign key (chat_id) references chats(chat_id) on delete cascade
            );

            create table if not exists giveaway_stats (
                chat_id integer not null,
                user_id integer not null,
                wins_count integer not null default 0,
                updated_at text not null,
                primary key (chat_id, user_id),
                foreign key (chat_id) references chats(chat_id) on delete cascade
            );

            create table if not exists giveaway_stat_awards (
                chat_id integer not null,
                pick_key text not null,
                pick_date text not null,
                created_at text not null,
                primary key (chat_id, pick_key, pick_date),
                foreign key (chat_id) references chats(chat_id) on delete cascade
            );

            create table if not exists star_payments (
                id integer primary key autoincrement,
                user_id integer not null,
                username text,
                full_name text not null,
                chat_id integer,
                amount integer not null,
                currency text not null,
                charge_id text not null,
                created_at text not null
            );

            create table if not exists pending_star_messages (
                payload text primary key,
                user_id integer not null,
                chat_id integer not null,
                text text not null,
                created_at text not null,
                foreign key (chat_id) references chats(chat_id) on delete cascade
            );

            create table if not exists secret_message_composes (
                compose_id text primary key,
                sender_id integer not null,
                chat_id integer not null,
                target_id integer not null,
                target_name text not null,
                created_at text not null
            );

            create table if not exists secret_messages (
                message_id text primary key,
                chat_id integer not null,
                sender_id integer not null,
                sender_username text,
                sender_name text not null,
                target_id integer not null,
                target_name text not null,
                text text not null,
                created_at text not null,
                delivered_at text
            );

            create table if not exists user_login_requests (
                login_id text primary key,
                secret_hash text not null,
                user_id integer,
                username text,
                full_name text,
                created_at text not null,
                expires_at text not null,
                approved_at text,
                consumed_at text
            );

            create table if not exists user_sessions (
                token_hash text primary key,
                user_id integer not null,
                username text,
                full_name text not null,
                created_at text not null,
                expires_at text not null,
                revoked_at text
            );

            create table if not exists user_subscriptions (
                user_id integer primary key,
                status text not null,
                expires_at text,
                telegram_payment_charge_id text,
                updated_at text not null
            );

            create table if not exists admin_feature_permissions (
                user_id integer not null,
                feature text not null,
                allowed integer not null default 0,
                updated_by integer,
                updated_at text not null,
                primary key (user_id, feature)
            );

            create table if not exists chat_admin_feature_permissions (
                chat_id integer not null,
                user_id integer not null,
                feature text not null,
                allowed integer not null default 0,
                updated_by integer,
                updated_at text not null,
                primary key (chat_id, user_id, feature),
                foreign key (chat_id) references chats(chat_id) on delete cascade
            );

            create table if not exists chat_telegram_admins (
                chat_id integer not null,
                user_id integer not null,
                username text,
                full_name text not null,
                status text not null default 'administrator',
                custom_title text,
                is_bot integer not null default 0,
                updated_at text not null,
                primary key (chat_id, user_id),
                foreign key (chat_id) references chats(chat_id) on delete cascade
            );
            create index if not exists idx_chat_telegram_admins_user
                on chat_telegram_admins(user_id, chat_id);

            create table if not exists quotes (
                id integer primary key autoincrement,
                chat_id integer not null,
                text text not null,
                author_name text,
                added_by integer,
                created_at text not null,
                foreign key (chat_id) references chats(chat_id) on delete cascade
            );

            create table if not exists birthdays (
                id integer primary key autoincrement,
                chat_id integer not null,
                day integer not null,
                month integer not null,
                text text not null,
                added_by integer,
                created_at text not null,
                foreign key (chat_id) references chats(chat_id) on delete cascade
            );

            create table if not exists advertisements (
                id integer primary key autoincrement,
                chat_id integer not null,
                text text not null,
                enabled integer not null default 0,
                start_time text not null default '09:00',
                interval_minutes integer not null default 180,
                duration_type text not null default 'unlimited',
                start_mode text not null default 'scheduled',
                scheduled_at text,
                topic_thread_id integer,
                first_sent_at text,
                last_sent_at text,
                last_error text,
                created_by integer,
                created_at text not null,
                updated_at text not null,
                foreign key (chat_id) references chats(chat_id) on delete cascade
            );

            create table if not exists advertisement_settings (
                chat_id integer primary key,
                enabled integer not null default 0,
                start_time text not null default '09:00',
                interval_minutes integer not null default 180,
                next_ad_index integer not null default 0,
                last_sent_at text,
                updated_by integer,
                updated_at text not null,
                foreign key (chat_id) references chats(chat_id) on delete cascade
            );

            create table if not exists advertisement_attachments (
                id integer primary key autoincrement,
                advertisement_id integer not null,
                media_type text not null,
                file_id text not null,
                filename text not null default '',
                position integer not null default 0,
                foreign key (advertisement_id) references advertisements(id) on delete cascade
            );

            create table if not exists birthday_sent (
                chat_id integer not null,
                birthday_id integer not null,
                sent_date text not null,
                primary key (chat_id, birthday_id, sent_date),
                foreign key (chat_id) references chats(chat_id) on delete cascade
            );

            create table if not exists blacklist_words (
                chat_id integer not null,
                word text not null,
                added_by integer,
                created_at text not null,
                primary key (chat_id, word),
                foreign key (chat_id) references chats(chat_id) on delete cascade
            );

            create table if not exists roll_mute_settings (
                chat_id integer primary key,
                mute_minutes integer not null default 60,
                cooldown_minutes integer not null default 30,
                updated_by integer,
                updated_at text not null,
                last_used_at text,
                foreign key (chat_id) references chats(chat_id) on delete cascade
            );

            create table if not exists roll_mute_stats (
                chat_id integer not null,
                user_id integer not null,
                unlucky_count integer not null default 0,
                updated_at text not null,
                primary key (chat_id, user_id),
                foreign key (chat_id) references chats(chat_id) on delete cascade
            );

            create table if not exists quiet_settings (
                chat_id integer primary key,
                reply_text text,
                media_type text,
                media_file_id text,
                updated_by integer,
                updated_at text not null,
                foreign key (chat_id) references chats(chat_id) on delete cascade
            );

            create table if not exists quiet_admins (
                chat_id integer not null,
                user_id integer not null,
                username text,
                full_name text not null,
                reason text not null default '',
                until_at text not null,
                created_by integer,
                created_at text not null,
                primary key (chat_id, user_id),
                foreign key (chat_id) references chats(chat_id) on delete cascade
            );

            create table if not exists chat_moderator_roles (
                chat_id integer not null,
                user_id integer not null,
                role text not null,
                granted_by integer,
                granted_at text not null,
                expires_at text,
                active integer not null default 1,
                primary key (chat_id, user_id),
                foreign key (chat_id) references chats(chat_id) on delete cascade
            );

            create index if not exists idx_chat_moderator_roles_active
                on chat_moderator_roles(chat_id, active, expires_at);

            create table if not exists chat_moderation_warnings (
                id integer primary key autoincrement,
                chat_id integer not null,
                user_id integer not null,
                moderator_id integer not null,
                reason text not null default '',
                created_at text not null,
                foreign key (chat_id) references chats(chat_id) on delete cascade
            );

            create index if not exists idx_chat_moderation_warnings_target
                on chat_moderation_warnings(chat_id, user_id, created_at);

            create table if not exists chat_moderator_actions (
                id integer primary key autoincrement,
                chat_id integer not null,
                moderator_id integer not null,
                target_user_id integer not null,
                action text not null,
                duration_minutes integer,
                reason text not null default '',
                created_at text not null,
                foreign key (chat_id) references chats(chat_id) on delete cascade
            );

            create index if not exists idx_chat_moderator_actions_target
                on chat_moderator_actions(chat_id, target_user_id, action, created_at);

            create table if not exists chat_moderator_votes (
                chat_id integer not null,
                voter_id integer not null,
                moderator_id integer not null,
                vote_date text not null,
                created_at text not null,
                updated_at text not null,
                primary key (chat_id, voter_id),
                foreign key (chat_id) references chats(chat_id) on delete cascade
            );

            create index if not exists idx_chat_moderator_votes_moderator
                on chat_moderator_votes(chat_id, moderator_id);

            create table if not exists chat_lock_settings (
                chat_id integer primary key,
                enabled integer not null default 0,
                reason text not null default '',
                until_at text,
                updated_by integer,
                updated_at text not null,
                foreign key (chat_id) references chats(chat_id) on delete cascade
            );

            create table if not exists chat_slow_mode_settings (
                chat_id integer primary key,
                delay_seconds integer not null default 0,
                updated_by integer,
                updated_at text not null,
                foreign key (chat_id) references chats(chat_id) on delete cascade
            );

            create table if not exists dig_players (
                chat_id integer not null,
                user_id integer not null,
                username text,
                full_name text not null,
                coins integer not null default 0,
                total_depth integer not null default 0,
                best_session_depth integer not null default 0,
                luck integer not null default 100,
                last_luck_at text not null,
                last_dig_at text,
                created_at text not null,
                updated_at text not null,
                primary key (chat_id, user_id),
                foreign key (chat_id) references chats(chat_id) on delete cascade
            );

            create table if not exists dig_items (
                chat_id integer not null,
                user_id integer not null,
                item_key text not null,
                quantity integer not null default 0,
                updated_at text not null,
                primary key (chat_id, user_id, item_key),
                foreign key (chat_id, user_id) references dig_players(chat_id, user_id) on delete cascade
            );

            create table if not exists dig_player_tags (
                user_id integer primary key,
                tag text not null,
                updated_at text not null
            );

            create table if not exists miniapp_profile_roles (
                user_id integer primary key,
                label text not null,
                emoji text,
                color text,
                granted_by integer,
                updated_at text not null
            );

            create table if not exists dig_blocked_users (
                user_id integer primary key,
                reason text not null default '',
                blocked_by integer,
                created_at text not null
            );

            create table if not exists dig_achievements (
                chat_id integer not null,
                user_id integer not null,
                achievement_key text not null,
                created_at text not null,
                primary key (chat_id, user_id, achievement_key),
                foreign key (chat_id, user_id) references dig_players(chat_id, user_id) on delete cascade
            );

            create table if not exists dig_progress (
                user_id integer primary key,
                xp integer not null default 0,
                level integer not null default 1,
                streak integer not null default 0,
                selected_route text not null default 'old_mine',
                last_dig_date text,
                updated_at text not null
            );

            create table if not exists dig_sessions (
                user_id integer primary key,
                depth integer not null default 0,
                luck_before integer not null default 100,
                route_key text not null,
                route_data text not null,
                used_effects text not null default '[]',
                started_at text not null,
                updated_at text not null
            );

            create table if not exists interactive_dig_sessions (
                id text primary key,
                user_id integer not null,
                chat_id integer not null,
                status text not null default 'active',
                route_key text not null,
                depth integer not null default 0,
                durability integer not null default 3,
                temporary_coins integer not null default 0,
                luck_snapshot integer not null default 100,
                equipment_snapshot text not null default '{}',
                cells_json text not null default '[]',
                used_cells_json text not null default '[]',
                message_id integer,
                processing integer not null default 0,
                created_at text not null,
                updated_at text not null
            );

            create unique index if not exists interactive_dig_sessions_active_user_uidx
            on interactive_dig_sessions(user_id)
            where status = 'active';

            create table if not exists dig_weekly_depth (
                week_start text not null,
                user_id integer not null,
                depth integer not null default 0,
                primary key (week_start, user_id)
            );

            create table if not exists gold_ticket_games (
                user_id integer primary key,
                cells_json text not null,
                opened_json text not null default '[]',
                attempts_left integer not null default 3,
                created_at text not null,
                updated_at text not null
            );

            create table if not exists super_ticket_games (
                user_id integer primary key,
                cells_json text not null,
                opened_json text not null default '[]',
                attempts_left integer not null default 10,
                created_at text not null,
                updated_at text not null
            );

            create table if not exists dig_contracts (
                user_id integer not null,
                contract_date text not null,
                contract_key text not null,
                target integer not null,
                progress integer not null default 0,
                claimed integer not null default 0,
                primary key (user_id, contract_date, contract_key)
            );

            create table if not exists dig_expeditions (
                chat_id integer not null,
                expedition_date text not null,
                target integer not null,
                progress integer not null default 0,
                completed integer not null default 0,
                primary key (chat_id, expedition_date)
            );

            create table if not exists dig_expedition_contributors (
                chat_id integer not null,
                expedition_date text not null,
                user_id integer not null,
                depth integer not null default 0,
                rewarded integer not null default 0,
                primary key (chat_id, expedition_date, user_id)
            );
            """
        )
        self._migrate_reply_media()
        self._migrate_alarm_settings()
        self._migrate_alarm_api_settings()
        self._migrate_advertisements()
        self._migrate_global_dig_game()
        self._conn.execute(
            "delete from star_payments where charge_id <> '' and id not in "
            "(select min(id) from star_payments where charge_id <> '' group by charge_id)"
        )
        self._conn.execute(
            "create unique index if not exists star_payments_charge_uidx "
            "on star_payments(charge_id) where charge_id <> ''"
        )
        self._conn.commit()

    def _migrate_reply_media(self) -> None:
        for table in ("auto_replies", "trigger_replies"):
            columns = {
                row["name"]
                for row in self._conn.execute(f"pragma table_info({table})").fetchall()
            }
            if "media_type" not in columns:
                self._conn.execute(f"alter table {table} add column media_type text")
            if "media_file_id" not in columns:
                self._conn.execute(f"alter table {table} add column media_file_id text")

    def _migrate_alarm_settings(self) -> None:
        columns = {
            row["name"]
            for row in self._conn.execute("pragma table_info(alarm_settings)").fetchall()
        }
        if "alarm_text" not in columns:
            self._conn.execute("alter table alarm_settings add column alarm_text text")
        if "clear_text" not in columns:
            self._conn.execute("alter table alarm_settings add column clear_text text")
        if "reactions_json" not in columns:
            self._conn.execute("alter table alarm_settings add column reactions_json text")
        if "alarm_thread_id" not in columns:
            self._conn.execute("alter table alarm_settings add column alarm_thread_id integer")

    def _migrate_alarm_api_settings(self) -> None:
        columns = {
            row["name"]
            for row in self._conn.execute("pragma table_info(alarm_api_settings)").fetchall()
        }
        if "last_notified_status" not in columns:
            self._conn.execute("alter table alarm_api_settings add column last_notified_status text")
        if "last_alarm_message_id" not in columns:
            self._conn.execute("alter table alarm_api_settings add column last_alarm_message_id integer")
        if "last_clear_message_id" not in columns:
            self._conn.execute("alter table alarm_api_settings add column last_clear_message_id integer")
        if "last_alarm_action_message_id" not in columns:
            self._conn.execute("alter table alarm_api_settings add column last_alarm_action_message_id integer")
        if "last_clear_action_message_id" not in columns:
            self._conn.execute("alter table alarm_api_settings add column last_clear_action_message_id integer")

    def _migrate_advertisements(self) -> None:
        columns = {
            row["name"]
            for row in self._conn.execute("pragma table_info(advertisements)").fetchall()
        }
        additions = {
            "enabled": "integer not null default 0",
            "start_time": "text not null default '09:00'",
            "interval_minutes": "integer not null default 180",
            "duration_type": "text not null default 'unlimited'",
            "start_mode": "text not null default 'scheduled'",
            "scheduled_at": "text",
            "topic_thread_id": "integer",
            "first_sent_at": "text",
            "last_sent_at": "text",
            "last_error": "text",
        }
        added_schedule = False
        for name, definition in additions.items():
            if name not in columns:
                self._conn.execute(f"alter table advertisements add column {name} {definition}")
                added_schedule = True
        if added_schedule:
            self._conn.execute(
                """
                update advertisements
                set enabled = coalesce((select enabled from advertisement_settings where chat_id = advertisements.chat_id), 0),
                    start_time = coalesce((select start_time from advertisement_settings where chat_id = advertisements.chat_id), '09:00'),
                    interval_minutes = coalesce((select interval_minutes from advertisement_settings where chat_id = advertisements.chat_id), 180),
                    last_sent_at = (select last_sent_at from advertisement_settings where chat_id = advertisements.chat_id)
                """
            )

    def _migrate_global_dig_game(self) -> None:
        old_players = self._conn.execute(
            """
            select chat_id, user_id, username, full_name, coins, total_depth, best_session_depth,
                   luck, last_luck_at, last_dig_at, created_at, updated_at
            from dig_players
            where chat_id != ?
            """,
            (DIG_GLOBAL_CHAT_ID,),
        ).fetchall()
        if not old_players:
            return

        players = self._conn.execute(
            """
            select chat_id, user_id, username, full_name, coins, total_depth, best_session_depth,
                   luck, last_luck_at, last_dig_at, created_at, updated_at
            from dig_players
            order by updated_at
            """
        ).fetchall()
        items = self._conn.execute(
            "select user_id, item_key, quantity, updated_at from dig_items"
        ).fetchall()
        achievements = self._conn.execute(
            "select user_id, achievement_key, created_at from dig_achievements"
        ).fetchall()

        merged_players: dict[int, dict] = {}
        for row in players:
            user_id = int(row["user_id"])
            current = merged_players.get(user_id)
            if current is None:
                merged_players[user_id] = dict(row)
                continue
            current["coins"] += int(row["coins"])
            current["total_depth"] += int(row["total_depth"])
            current["best_session_depth"] = max(int(current["best_session_depth"]), int(row["best_session_depth"]))
            current["created_at"] = min(current["created_at"], row["created_at"])
            if row["updated_at"] >= current["updated_at"]:
                current["username"] = row["username"]
                current["full_name"] = row["full_name"]
                current["luck"] = row["luck"]
                current["last_luck_at"] = row["last_luck_at"]
                current["updated_at"] = row["updated_at"]
            if row["last_dig_at"] and (not current["last_dig_at"] or row["last_dig_at"] > current["last_dig_at"]):
                current["last_dig_at"] = row["last_dig_at"]

        merged_items: dict[tuple[int, str], dict] = {}
        for row in items:
            key = (int(row["user_id"]), row["item_key"])
            current = merged_items.get(key)
            if current is None:
                merged_items[key] = dict(row)
                continue
            current["quantity"] += int(row["quantity"])
            current["updated_at"] = max(current["updated_at"], row["updated_at"])

        merged_achievements: dict[tuple[int, str], dict] = {}
        for row in achievements:
            key = (int(row["user_id"]), row["achievement_key"])
            current = merged_achievements.get(key)
            if current is None or row["created_at"] < current["created_at"]:
                merged_achievements[key] = dict(row)

        self._conn.execute("delete from dig_achievements")
        self._conn.execute("delete from dig_items")
        self._conn.execute("delete from dig_players")
        for player in merged_players.values():
            self._conn.execute(
                """
                insert into dig_players (
                    chat_id, user_id, username, full_name, coins, total_depth, best_session_depth,
                    luck, last_luck_at, last_dig_at, created_at, updated_at
                )
                values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    DIG_GLOBAL_CHAT_ID,
                    player["user_id"],
                    player["username"],
                    player["full_name"],
                    player["coins"],
                    player["total_depth"],
                    player["best_session_depth"],
                    player["luck"],
                    player["last_luck_at"],
                    player["last_dig_at"],
                    player["created_at"],
                    player["updated_at"],
                ),
            )
        for item in merged_items.values():
            self._conn.execute(
                """
                insert into dig_items (chat_id, user_id, item_key, quantity, updated_at)
                values (?, ?, ?, ?, ?)
                """,
                (DIG_GLOBAL_CHAT_ID, item["user_id"], item["item_key"], item["quantity"], item["updated_at"]),
            )
        for achievement in merged_achievements.values():
            self._conn.execute(
                """
                insert into dig_achievements (chat_id, user_id, achievement_key, created_at)
                values (?, ?, ?, ?)
                """,
                (DIG_GLOBAL_CHAT_ID, achievement["user_id"], achievement["achievement_key"], achievement["created_at"]),
            )

    def upsert_chat(self, chat_id: int, title: str, chat_type: str, username: str | None) -> None:
        self._conn.execute(
            """
            insert into chats (chat_id, title, type, username, updated_at)
            values (?, ?, ?, ?, ?)
            on conflict(chat_id) do update set
                title = excluded.title,
                type = excluded.type,
                username = excluded.username,
                updated_at = excluded.updated_at
            """,
            (chat_id, title, chat_type, username, utc_now()),
        )
        self._conn.commit()

    def get_dig_session(self, user_id: int) -> dict | None:
        row = self._conn.execute(
            """
            select user_id, depth, luck_before, route_key, route_data, used_effects,
                   started_at, updated_at
            from dig_sessions where user_id = ?
            """,
            (int(user_id),),
        ).fetchone()
        return dict(row) if row else None

    def save_dig_session(
        self,
        user_id: int,
        depth: int,
        luck_before: int,
        route_key: str,
        route_data: str,
        used_effects: str,
        started_at: str,
    ) -> None:
        now = utc_now()
        self._conn.execute(
            """
            insert into dig_sessions
                (user_id, depth, luck_before, route_key, route_data, used_effects, started_at, updated_at)
            values (?, ?, ?, ?, ?, ?, ?, ?)
            on conflict(user_id) do update set
                depth = excluded.depth,
                luck_before = excluded.luck_before,
                route_key = excluded.route_key,
                route_data = excluded.route_data,
                used_effects = excluded.used_effects,
                started_at = excluded.started_at,
                updated_at = excluded.updated_at
            """,
            (int(user_id), int(depth), int(luck_before), route_key, route_data, used_effects, started_at, now),
        )
        self._conn.commit()

    def clear_dig_session(self, user_id: int) -> None:
        self._conn.execute("delete from dig_sessions where user_id = ?", (int(user_id),))
        self._conn.commit()

    def get_active_interactive_dig_session(self, user_id: int) -> dict | None:
        row = self._conn.execute(
            """
            select id, user_id, chat_id, status, route_key, depth, durability, temporary_coins,
                   luck_snapshot, equipment_snapshot, cells_json, used_cells_json, message_id,
                   processing, created_at, updated_at
            from interactive_dig_sessions
            where user_id = ? and status = 'active'
            """,
            (int(user_id),),
        ).fetchone()
        return dict(row) if row else None

    def get_interactive_dig_session(self, session_id: str) -> dict | None:
        row = self._conn.execute(
            """
            select id, user_id, chat_id, status, route_key, depth, durability, temporary_coins,
                   luck_snapshot, equipment_snapshot, cells_json, used_cells_json, message_id,
                   processing, created_at, updated_at
            from interactive_dig_sessions
            where id = ?
            """,
            (str(session_id),),
        ).fetchone()
        return dict(row) if row else None

    def create_interactive_dig_session(
        self,
        *,
        session_id: str,
        user_id: int,
        chat_id: int,
        route_key: str,
        depth: int,
        durability: int,
        temporary_coins: int,
        luck_snapshot: int,
        equipment_snapshot: str,
        cells_json: str,
        used_cells_json: str = "[]",
        message_id: int | None = None,
    ) -> dict:
        now = utc_now()
        self._conn.execute(
            """
            insert into interactive_dig_sessions (
                id, user_id, chat_id, status, route_key, depth, durability, temporary_coins,
                luck_snapshot, equipment_snapshot, cells_json, used_cells_json, message_id,
                processing, created_at, updated_at
            )
            values (?, ?, ?, 'active', ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?)
            """,
            (
                str(session_id),
                int(user_id),
                int(chat_id),
                route_key,
                int(depth),
                int(durability),
                int(temporary_coins),
                int(luck_snapshot),
                equipment_snapshot,
                cells_json,
                used_cells_json,
                int(message_id) if message_id is not None else None,
                now,
                now,
            ),
        )
        self._conn.commit()
        row = self.get_interactive_dig_session(session_id)
        if row is None:
            raise RuntimeError("interactive dig session was not created")
        return row

    def update_interactive_dig_session(
        self,
        session_id: str,
        *,
        depth: int | None = None,
        durability: int | None = None,
        temporary_coins: int | None = None,
        cells_json: str | None = None,
        used_cells_json: str | None = None,
        equipment_snapshot: str | None = None,
        message_id: int | None = None,
        processing: int | None = None,
    ) -> None:
        fields: list[str] = []
        values: list[object] = []
        for name, value in (
            ("depth", depth),
            ("durability", durability),
            ("temporary_coins", temporary_coins),
            ("cells_json", cells_json),
            ("used_cells_json", used_cells_json),
            ("equipment_snapshot", equipment_snapshot),
            ("message_id", message_id),
            ("processing", processing),
        ):
            if value is not None:
                fields.append(f"{name} = ?")
                values.append(value)
        if not fields:
            return
        fields.append("updated_at = ?")
        values.append(utc_now())
        values.append(str(session_id))
        self._conn.execute(
            f"update interactive_dig_sessions set {', '.join(fields)} where id = ?",
            tuple(values),
        )
        self._conn.commit()

    def lock_interactive_dig_cell(self, session_id: str, user_id: int, depth: int, cell_index: int) -> dict | None:
        try:
            self._conn.execute("begin immediate")
            row = self._conn.execute(
                """
                select id, user_id, chat_id, status, route_key, depth, durability, temporary_coins,
                       luck_snapshot, equipment_snapshot, cells_json, used_cells_json, message_id,
                       processing, created_at, updated_at
                from interactive_dig_sessions
                where id = ? and user_id = ? and status = 'active'
                """,
                (str(session_id), int(user_id)),
            ).fetchone()
            if row is None:
                self._conn.rollback()
                return None
            data = dict(row)
            if int(data["processing"]) or int(data["depth"]) != int(depth):
                self._conn.rollback()
                return None
            used = set(json.loads(data["used_cells_json"] or "[]"))
            if int(cell_index) in used:
                self._conn.rollback()
                return None
            self._conn.execute(
                "update interactive_dig_sessions set processing = 1, updated_at = ? where id = ?",
                (utc_now(), str(session_id)),
            )
            self._conn.commit()
            data["processing"] = 1
            return data
        except Exception:
            with suppress(Exception):
                self._conn.rollback()
            raise

    def finish_interactive_dig_session(self, session_id: str, status: str = "finished") -> None:
        self._conn.execute(
            """
            update interactive_dig_sessions
            set status = ?, processing = 0, updated_at = ?
            where id = ?
            """,
            (status, utc_now(), str(session_id)),
        )
        self._conn.commit()

    def get_gold_ticket_game(self, user_id: int) -> dict | None:
        row = self._conn.execute(
            """
            select user_id, cells_json, opened_json, attempts_left, created_at, updated_at
            from gold_ticket_games where user_id = ?
            """,
            (int(user_id),),
        ).fetchone()
        return dict(row) if row else None

    def save_gold_ticket_game(
        self,
        user_id: int,
        cells_json: str,
        opened_json: str,
        attempts_left: int,
        created_at: str,
    ) -> None:
        now = utc_now()
        self._conn.execute(
            """
            insert into gold_ticket_games
                (user_id, cells_json, opened_json, attempts_left, created_at, updated_at)
            values (?, ?, ?, ?, ?, ?)
            on conflict(user_id) do update set
                cells_json = excluded.cells_json,
                opened_json = excluded.opened_json,
                attempts_left = excluded.attempts_left,
                updated_at = excluded.updated_at
            """,
            (int(user_id), cells_json, opened_json, max(0, int(attempts_left)), created_at, now),
        )
        self._conn.commit()

    def clear_gold_ticket_game(self, user_id: int) -> None:
        self._conn.execute("delete from gold_ticket_games where user_id = ?", (int(user_id),))
        self._conn.commit()

    def get_super_ticket_game(self, user_id: int) -> dict | None:
        row = self._conn.execute(
            "select user_id, cells_json, opened_json, attempts_left, created_at, updated_at "
            "from super_ticket_games where user_id = ?",
            (int(user_id),),
        ).fetchone()
        return dict(row) if row else None

    def save_super_ticket_game(
        self, user_id: int, cells_json: str, opened_json: str, attempts_left: int, created_at: str
    ) -> None:
        self._conn.execute(
            """
            insert into super_ticket_games
                (user_id, cells_json, opened_json, attempts_left, created_at, updated_at)
            values (?, ?, ?, ?, ?, ?)
            on conflict(user_id) do update set
                cells_json = excluded.cells_json,
                opened_json = excluded.opened_json,
                attempts_left = excluded.attempts_left,
                updated_at = excluded.updated_at
            """,
            (int(user_id), cells_json, opened_json, max(0, int(attempts_left)), created_at, utc_now()),
        )
        self._conn.commit()

    def clear_super_ticket_game(self, user_id: int) -> None:
        self._conn.execute("delete from super_ticket_games where user_id = ?", (int(user_id),))
        self._conn.commit()

    def list_chats(self) -> list[RegisteredChat]:
        rows = self._conn.execute(
            "select chat_id, title, type, username, updated_at from chats order by title collate nocase"
        ).fetchall()
        return [RegisteredChat(**dict(row)) for row in rows]

    def get_chat(self, chat_id: int) -> RegisteredChat | None:
        row = self._conn.execute(
            "select chat_id, title, type, username, updated_at from chats where chat_id = ?",
            (chat_id,),
        ).fetchone()
        return RegisteredChat(**dict(row)) if row else None

    def delete_chat(self, chat_id: int) -> None:
        self._conn.execute("delete from chats where chat_id = ?", (chat_id,))
        self._conn.commit()

    def set_reply(
        self,
        chat_id: int,
        username: str,
        text: str,
        updated_by: int | None,
        media_type: str | None = None,
        media_file_id: str | None = None,
    ) -> None:
        self._conn.execute(
            """
            insert into auto_replies (chat_id, username, text, media_type, media_file_id, updated_by, updated_at)
            values (?, ?, ?, ?, ?, ?, ?)
            on conflict(chat_id, username) do update set
                text = excluded.text,
                media_type = excluded.media_type,
                media_file_id = excluded.media_file_id,
                updated_by = excluded.updated_by,
                updated_at = excluded.updated_at
            """,
            (chat_id, normalize_username(username), text.strip(), media_type, media_file_id, updated_by, utc_now()),
        )
        self._conn.commit()

    def delete_reply(self, chat_id: int, username: str) -> bool:
        cur = self._conn.execute(
            "delete from auto_replies where chat_id = ? and username = ?",
            (chat_id, normalize_username(username)),
        )
        self._conn.commit()
        return cur.rowcount > 0

    def get_reply(self, chat_id: int, username: str) -> AutoReply | None:
        row = self._conn.execute(
            """
            select chat_id, username, text, media_type, media_file_id, updated_by, updated_at
            from auto_replies
            where chat_id = ? and username = ?
            """,
            (chat_id, normalize_username(username)),
        ).fetchone()
        return AutoReply(**dict(row)) if row else None

    def list_replies(self, chat_id: int) -> list[AutoReply]:
        rows = self._conn.execute(
            """
            select chat_id, username, text, media_type, media_file_id, updated_by, updated_at
            from auto_replies
            where chat_id = ?
            order by username collate nocase
            """,
            (chat_id,),
        ).fetchall()
        return [AutoReply(**dict(row)) for row in rows]

    def replies_for_mentions(self, chat_id: int, usernames: Iterable[str]) -> list[AutoReply]:
        normalized = sorted({normalize_username(item) for item in usernames if item})
        if not normalized:
            return []

        placeholders = ",".join("?" for _ in normalized)
        rows = self._conn.execute(
            f"""
            select chat_id, username, text, media_type, media_file_id, updated_by, updated_at
            from auto_replies
            where chat_id = ? and username in ({placeholders})
            order by username collate nocase
            """,
            (chat_id, *normalized),
        ).fetchall()
        return [AutoReply(**dict(row)) for row in rows]

    def set_trigger(
        self,
        chat_id: int,
        trigger: str,
        text: str,
        updated_by: int | None,
        media_type: str | None = None,
        media_file_id: str | None = None,
    ) -> None:
        self._conn.execute(
            """
            insert into trigger_replies (chat_id, trigger, text, media_type, media_file_id, updated_by, updated_at)
            values (?, ?, ?, ?, ?, ?, ?)
            on conflict(chat_id, trigger) do update set
                text = excluded.text,
                media_type = excluded.media_type,
                media_file_id = excluded.media_file_id,
                updated_by = excluded.updated_by,
                updated_at = excluded.updated_at
            """,
            (chat_id, normalize_trigger(trigger), text.strip(), media_type, media_file_id, updated_by, utc_now()),
        )
        self._conn.commit()

    def delete_trigger(self, chat_id: int, trigger: str) -> bool:
        normalized = normalize_trigger(trigger)
        self._conn.execute(
            "delete from trigger_aliases where chat_id = ? and trigger = ?",
            (chat_id, normalized),
        )
        self._conn.execute(
            "delete from trigger_reply_variants where chat_id = ? and trigger = ?",
            (chat_id, normalized),
        )
        cur = self._conn.execute(
            "delete from trigger_replies where chat_id = ? and trigger = ?",
            (chat_id, normalized),
        )
        self._conn.commit()
        return cur.rowcount > 0

    def list_triggers(self, chat_id: int) -> list[TriggerReply]:
        rows = self._conn.execute(
            """
            select chat_id, trigger, text, media_type, media_file_id, updated_by, updated_at
            from trigger_replies
            where chat_id = ?
            order by trigger collate nocase
            """,
            (chat_id,),
        ).fetchall()
        return [TriggerReply(**dict(row)) for row in rows]

    def replace_trigger_aliases(self, chat_id: int, trigger: str, aliases: list[str], updated_by: int | None) -> None:
        normalized = normalize_trigger(trigger)
        cleaned: list[str] = []
        for alias in aliases:
            normalized_alias = normalize_trigger(alias)
            if normalized_alias and normalized_alias != normalized and normalized_alias not in cleaned:
                cleaned.append(normalized_alias)
        self._conn.execute(
            "delete from trigger_aliases where chat_id = ? and trigger = ?",
            (chat_id, normalized),
        )
        now = utc_now()
        for alias in cleaned:
            self._conn.execute(
                """
                insert into trigger_aliases (chat_id, trigger, alias, updated_by, updated_at)
                values (?, ?, ?, ?, ?)
                """,
                (chat_id, normalized, alias, updated_by, now),
            )
        self._conn.commit()

    def list_trigger_aliases(self, chat_id: int, trigger: str) -> list[str]:
        rows = self._conn.execute(
            """
            select alias
            from trigger_aliases
            where chat_id = ? and trigger = ?
            order by alias collate nocase
            """,
            (chat_id, normalize_trigger(trigger)),
        ).fetchall()
        return [str(row["alias"]) for row in rows]

    def trigger_aliases_map(self, chat_id: int) -> dict[str, tuple[str, ...]]:
        rows = self._conn.execute(
            """
            select trigger, alias
            from trigger_aliases
            where chat_id = ?
            order by alias collate nocase
            """,
            (chat_id,),
        ).fetchall()
        result: dict[str, list[str]] = {}
        for row in rows:
            result.setdefault(str(row["trigger"]), []).append(str(row["alias"]))
        return {trigger: tuple(aliases) for trigger, aliases in result.items()}

    def replace_trigger_variants(
        self,
        chat_id: int,
        trigger: str,
        variants: list[dict[str, object]],
        updated_by: int | None,
    ) -> None:
        normalized = normalize_trigger(trigger)
        fallback_text = ""
        fallback_media_type = None
        fallback_media_file_id = None
        if variants:
            first = variants[0]
            fallback_text = str(first.get("text") or "").strip()
            fallback_media_type = str(first.get("media_type") or "") or None
            fallback_media_file_id = str(first.get("media_file_id") or "") or None
        self.set_trigger(chat_id, normalized, fallback_text, updated_by, fallback_media_type, fallback_media_file_id)
        self._conn.execute(
            "delete from trigger_reply_variants where chat_id = ? and trigger = ?",
            (chat_id, normalized),
        )
        now = utc_now()
        for position, variant in enumerate(variants):
            variant_type = str(variant.get("variant_type") or "text").strip() or "text"
            text = str(variant.get("text") or "").strip()
            media_type = str(variant.get("media_type") or "") or None
            media_file_id = str(variant.get("media_file_id") or "") or None
            self._conn.execute(
                """
                insert into trigger_reply_variants
                    (chat_id, trigger, variant_type, text, media_type, media_file_id, position, updated_by, updated_at)
                values (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (chat_id, normalized, variant_type, text, media_type, media_file_id, position, updated_by, now),
            )
        self._conn.commit()

    def list_trigger_variants(self, chat_id: int, trigger: str) -> list[TriggerReplyVariant]:
        normalized = normalize_trigger(trigger)
        rows = self._conn.execute(
            """
            select id, chat_id, trigger, variant_type, text, media_type, media_file_id, position, updated_by, updated_at
            from trigger_reply_variants
            where chat_id = ? and trigger = ?
            order by position, id
            """,
            (chat_id, normalized),
        ).fetchall()
        return [TriggerReplyVariant(**dict(row)) for row in rows]

    def list_trigger_answer_options(self, chat_id: int) -> list[TriggerReplyVariant | TriggerReply]:
        aliases = self.trigger_aliases_map(chat_id)
        variant_rows = self._conn.execute(
            """
            select id, chat_id, trigger, variant_type, text, media_type, media_file_id, position, updated_by, updated_at
            from trigger_reply_variants
            where chat_id = ?
            order by trigger collate nocase, position, id
            """,
            (chat_id,),
        ).fetchall()
        variants = [
            TriggerReplyVariant(**dict(row), aliases=aliases.get(str(row["trigger"]), ()))
            for row in variant_rows
        ]
        variant_keys = {(item.chat_id, item.trigger) for item in variants}
        fallback_rows = self._conn.execute(
            """
            select chat_id, trigger, text, media_type, media_file_id, updated_by, updated_at
            from trigger_replies
            where chat_id = ?
            order by trigger collate nocase
            """,
            (chat_id,),
        ).fetchall()
        fallbacks = [
            TriggerReply(**dict(row), aliases=aliases.get(str(row["trigger"]), ()))
            for row in fallback_rows
            if (int(row["chat_id"]), str(row["trigger"])) not in variant_keys
        ]
        return [*variants, *fallbacks]

    def upsert_seen_user(
        self,
        chat_id: int,
        user_id: int,
        username: str | None,
        full_name: str,
        is_bot: bool,
    ) -> None:
        self._conn.execute(
            """
            insert into seen_users (chat_id, user_id, username, full_name, is_bot, updated_at)
            values (?, ?, ?, ?, ?, ?)
            on conflict(chat_id, user_id) do update set
                username = excluded.username,
                full_name = excluded.full_name,
                is_bot = excluded.is_bot,
                updated_at = excluded.updated_at
            """,
            (chat_id, user_id, normalize_username(username) if username else None, full_name, int(is_bot), utc_now()),
        )
        self._conn.commit()

    def list_pickable_users(self, chat_id: int) -> list[SeenUser]:
        rows = self._conn.execute(
            """
            select chat_id, user_id, username, full_name, is_bot, updated_at
            from seen_users
            where chat_id = ? and is_bot = 0 and username is not null
            order by updated_at desc
            """,
            (chat_id,),
        ).fetchall()
        return [SeenUser(**dict(row)) for row in rows]

    def count_pickable_users_all(self) -> int:
        row = self._conn.execute(
            """
            select count(*) as total
            from seen_users
            where is_bot = 0 and username is not null
            """
        ).fetchone()
        return int(row["total"]) if row else 0

    def increment_participant_activity(self, chat_id: int, user_id: int, activity_date: str | None = None) -> None:
        day = activity_date or datetime.now(timezone.utc).date().isoformat()
        self._conn.execute(
            """
            insert into participant_activity_daily (chat_id, user_id, activity_date, messages_count, updated_at)
            values (?, ?, ?, 1, ?)
            on conflict(chat_id, user_id, activity_date) do update set
                messages_count = messages_count + 1,
                updated_at = excluded.updated_at
            """,
            (chat_id, user_id, day, utc_now()),
        )
        self._conn.commit()

    def top_participant_activity(
        self,
        chat_id: int,
        since_date: str | None = None,
        limit: int = 20,
    ) -> list[ParticipantActivity]:
        where = "where a.chat_id = ?"
        params: list[object] = [chat_id]
        if since_date is not None:
            where += " and a.activity_date >= ?"
            params.append(since_date)
        params.append(limit)
        rows = self._conn.execute(
            f"""
            select
                a.chat_id,
                a.user_id,
                u.username,
                coalesce(u.full_name, cast(a.user_id as text)) as full_name,
                sum(a.messages_count) as messages_count
            from participant_activity_daily a
            left join seen_users u on u.chat_id = a.chat_id and u.user_id = a.user_id
            {where}
            group by a.chat_id, a.user_id
            order by messages_count desc, u.full_name collate nocase
            limit ?
            """,
            tuple(params),
        ).fetchall()
        return [ParticipantActivity(**dict(row)) for row in rows]

    def list_admin_feature_permissions(self, chat_id: int, user_id: int | None = None) -> list[AdminFeaturePermission]:
        if user_id is None:
            rows = self._conn.execute(
                """
                select chat_id, user_id, feature, allowed, updated_by, updated_at
                from chat_admin_feature_permissions
                where chat_id = ?
                order by user_id, feature
                """,
                (chat_id,),
            ).fetchall()
        else:
            rows = self._conn.execute(
                """
                select chat_id, user_id, feature, allowed, updated_by, updated_at
                from chat_admin_feature_permissions
                where chat_id = ? and user_id = ?
                order by feature
                """,
                (chat_id, user_id),
            ).fetchall()
        return [AdminFeaturePermission(**dict(row)) for row in rows]

    def admin_feature_allowed(self, chat_id: int, user_id: int, feature: str, default: bool = False) -> bool:
        value = self.admin_feature_permission(chat_id, user_id, feature)
        return value if value is not None else default

    def admin_feature_permission(self, chat_id: int, user_id: int, feature: str) -> bool | None:
        row = self._conn.execute(
            """
            select allowed
            from chat_admin_feature_permissions
            where chat_id = ? and user_id = ? and feature = ?
            """,
            (chat_id, user_id, feature),
        ).fetchone()
        return bool(row["allowed"]) if row else None

    def has_admin_feature_permission(self, chat_id: int, user_id: int, feature: str) -> bool:
        row = self._conn.execute(
            """
            select 1
            from chat_admin_feature_permissions
            where chat_id = ? and user_id = ? and feature = ?
            """,
            (chat_id, user_id, feature),
        ).fetchone()
        return row is not None

    def set_admin_feature_permission(
        self,
        chat_id: int,
        user_id: int,
        feature: str,
        allowed: bool,
        updated_by: int | None,
    ) -> None:
        self._conn.execute(
            """
            insert into chat_admin_feature_permissions (chat_id, user_id, feature, allowed, updated_by, updated_at)
            values (?, ?, ?, ?, ?, ?)
            on conflict(chat_id, user_id, feature) do update set
                allowed = excluded.allowed,
                updated_by = excluded.updated_by,
                updated_at = excluded.updated_at
            """,
            (chat_id, user_id, feature, int(allowed), updated_by, utc_now()),
        )
        self._conn.commit()

    def user_admin_chat_ids(self, user_id: int) -> set[int]:
        rows = self._conn.execute(
            """
            select distinct chat_id
            from chat_admin_feature_permissions
            where user_id = ? and allowed = 1
            """,
            (user_id,),
        ).fetchall()
        return {int(row["chat_id"]) for row in rows}

    def user_telegram_admin_chat_ids(self, user_id: int) -> set[int]:
        rows = self._conn.execute(
            """
            select distinct chat_id
            from chat_telegram_admins
            where user_id = ? and is_bot = 0
            """,
            (int(user_id),),
        ).fetchall()
        return {int(row["chat_id"]) for row in rows}

    def replace_chat_telegram_admins(self, chat_id: int, admins: list[dict]) -> None:
        now = utc_now()
        with self._conn:
            self._conn.execute("delete from chat_telegram_admins where chat_id = ?", (int(chat_id),))
            for admin in admins:
                user_id = int(admin["user_id"])
                username = normalize_username(admin.get("username")) if admin.get("username") else None
                full_name = str(admin.get("full_name") or user_id)
                is_bot = int(bool(admin.get("is_bot")))
                self._conn.execute(
                    """
                    insert into chat_telegram_admins
                        (chat_id, user_id, username, full_name, status, custom_title, is_bot, updated_at)
                    values (?, ?, ?, ?, ?, ?, ?, ?)
                    on conflict(chat_id, user_id) do update set
                        username = excluded.username,
                        full_name = excluded.full_name,
                        status = excluded.status,
                        custom_title = excluded.custom_title,
                        is_bot = excluded.is_bot,
                        updated_at = excluded.updated_at
                    """,
                    (
                        int(chat_id),
                        user_id,
                        username,
                        full_name,
                        str(admin.get("status") or "administrator"),
                        admin.get("custom_title"),
                        is_bot,
                        now,
                    ),
                )
                self._conn.execute(
                    """
                    insert into seen_users (chat_id, user_id, username, full_name, is_bot, updated_at)
                    values (?, ?, ?, ?, ?, ?)
                    on conflict(chat_id, user_id) do update set
                        username = excluded.username,
                        full_name = excluded.full_name,
                        is_bot = excluded.is_bot,
                        updated_at = excluded.updated_at
                    """,
                    (int(chat_id), user_id, username, full_name, is_bot, now),
                )

    def list_chat_telegram_admins(self, chat_id: int) -> list[dict]:
        rows = self._conn.execute(
            """
            select
                chat_id,
                user_id,
                coalesce(username, '') as username,
                full_name,
                status,
                coalesce(custom_title, '') as custom_title,
                updated_at
            from chat_telegram_admins
            where chat_id = ? and is_bot = 0
            order by case status when 'creator' then 0 else 1 end, lower(full_name)
            """,
            (int(chat_id),),
        ).fetchall()
        return [dict(row) for row in rows]

    def get_seen_user_by_username(self, chat_id: int, username: str) -> SeenUser | None:
        row = self._conn.execute(
            """
            select chat_id, user_id, username, full_name, is_bot, updated_at
            from seen_users
            where chat_id = ? and username = ? and is_bot = 0
            """,
            (chat_id, normalize_username(username)),
        ).fetchone()
        return SeenUser(**dict(row)) if row else None

    def set_chat_moderator_role(
        self,
        chat_id: int,
        user_id: int,
        role: str,
        granted_by: int | None,
        expires_at: str | None = None,
    ) -> None:
        self._conn.execute(
            """
            insert into chat_moderator_roles (chat_id, user_id, role, granted_by, granted_at, expires_at, active)
            values (?, ?, ?, ?, ?, ?, 1)
            on conflict(chat_id, user_id) do update set
                role = excluded.role,
                granted_by = excluded.granted_by,
                granted_at = excluded.granted_at,
                expires_at = excluded.expires_at,
                active = 1
            """,
            (chat_id, user_id, role, granted_by, utc_now(), expires_at),
        )
        self._conn.commit()

    def clear_chat_moderator_role(self, chat_id: int, user_id: int) -> bool:
        cur = self._conn.execute(
            """
            update chat_moderator_roles
            set active = 0
            where chat_id = ? and user_id = ? and active = 1
            """,
            (chat_id, user_id),
        )
        self._conn.commit()
        return cur.rowcount > 0

    def clear_all_chat_moderator_roles(self, user_id: int, role: str | None = None) -> int:
        if role:
            cur = self._conn.execute(
                """
                update chat_moderator_roles
                set active = 0
                where user_id = ? and role = ? and active = 1
                """,
                (int(user_id), role),
            )
        else:
            cur = self._conn.execute(
                """
                update chat_moderator_roles
                set active = 0
                where user_id = ? and active = 1
                """,
                (int(user_id),),
            )
        self._conn.commit()
        return int(cur.rowcount)

    def get_chat_moderator_role(self, chat_id: int, user_id: int, now: str | None = None) -> dict | None:
        check_at = now or utc_now()
        row = self._conn.execute(
            """
            select chat_id, user_id, role, granted_by, granted_at, expires_at, active
            from chat_moderator_roles
            where chat_id = ? and user_id = ? and active = 1
              and (expires_at is null or expires_at > ?)
            """,
            (chat_id, user_id, check_at),
        ).fetchone()
        return dict(row) if row else None

    def list_chat_moderators(self, chat_id: int, now: str | None = None) -> list[dict]:
        check_at = now or utc_now()
        rows = self._conn.execute(
            """
            select
                r.chat_id,
                r.user_id,
                r.role,
                r.granted_by,
                r.granted_at,
                r.expires_at,
                coalesce(u.username, '') as username,
                coalesce(u.full_name, cast(r.user_id as text)) as full_name,
                coalesce(v.votes_count, 0) as votes_count
            from chat_moderator_roles r
            left join seen_users u on u.chat_id = r.chat_id and u.user_id = r.user_id
            left join (
                select chat_id, moderator_id, count(*) as votes_count
                from chat_moderator_votes
                where chat_id = ?
                group by chat_id, moderator_id
            ) v on v.chat_id = r.chat_id and v.moderator_id = r.user_id
            where r.chat_id = ? and r.active = 1
              and (r.expires_at is null or r.expires_at > ?)
            """,
            (chat_id, chat_id, check_at),
        ).fetchall()
        return [dict(row) for row in rows]

    def list_all_chat_moderators(self, now: str | None = None) -> list[dict]:
        check_at = now or utc_now()
        rows = self._conn.execute(
            """
            select
                r.chat_id,
                r.user_id,
                r.role,
                r.granted_by,
                r.granted_at,
                r.expires_at,
                coalesce(c.title, cast(r.chat_id as text)) as chat_title,
                coalesce(u.username, '') as username,
                coalesce(u.full_name, cast(r.user_id as text)) as full_name
            from chat_moderator_roles r
            left join chats c on c.chat_id = r.chat_id
            left join (
                select user_id, max(nullif(username, '')) as username, max(nullif(full_name, '')) as full_name
                from seen_users
                where coalesce(is_bot, 0) = 0
                group by user_id
            ) u on u.user_id = r.user_id
            where r.active = 1
              and (r.expires_at is null or r.expires_at > ?)
            order by
                case r.role when 'senior' then 1 when 'moderator' then 2 when 'assistant' then 3 else 9 end,
                lower(coalesce(u.full_name, cast(r.user_id as text)))
            """,
            (check_at,),
        ).fetchall()
        return [dict(row) for row in rows]

    def add_moderation_warning(self, chat_id: int, user_id: int, moderator_id: int, reason: str) -> int:
        cur = self._conn.execute(
            """
            insert into chat_moderation_warnings (chat_id, user_id, moderator_id, reason, created_at)
            values (?, ?, ?, ?, ?)
            """,
            (chat_id, user_id, moderator_id, reason.strip()[:500], utc_now()),
        )
        self._conn.commit()
        return int(cur.lastrowid)

    def add_moderator_action(
        self,
        chat_id: int,
        moderator_id: int,
        target_user_id: int,
        action: str,
        duration_minutes: int | None = None,
        reason: str = "",
    ) -> int:
        cur = self._conn.execute(
            """
            insert into chat_moderator_actions
                (chat_id, moderator_id, target_user_id, action, duration_minutes, reason, created_at)
            values (?, ?, ?, ?, ?, ?, ?)
            """,
            (chat_id, moderator_id, target_user_id, action, duration_minutes, reason.strip()[:500], utc_now()),
        )
        self._conn.commit()
        return int(cur.lastrowid)

    def count_moderator_mutes_for_target(self, chat_id: int, target_user_id: int, since_at: str | None = None) -> int:
        params: list[object] = [chat_id, target_user_id, "mute"]
        where = "where chat_id = ? and target_user_id = ? and action = ?"
        if since_at is not None:
            where += " and created_at >= ?"
            params.append(since_at)
        row = self._conn.execute(
            f"select count(*) as total from chat_moderator_actions {where}",
            tuple(params),
        ).fetchone()
        return int(row["total"]) if row else 0

    def latest_active_moderator_mute(self, chat_id: int, target_user_id: int, now: str | None = None) -> dict | None:
        check_at = now or utc_now()
        check_dt = datetime.fromisoformat(check_at)
        rows = self._conn.execute(
            """
            select id, chat_id, moderator_id, target_user_id, action, duration_minutes, reason, created_at
            from chat_moderator_actions
            where chat_id = ? and target_user_id = ? and action in ('mute', 'unmute')
            order by id desc
            limit 20
            """,
            (chat_id, target_user_id),
        ).fetchall()
        for row in rows:
            item = dict(row)
            if item["action"] == "unmute":
                return None
            duration = item.get("duration_minutes")
            if not duration:
                return item
            expires_at = datetime.fromisoformat(str(item["created_at"])) + timedelta(minutes=int(duration))
            if expires_at > check_dt:
                return item
            return None
        return None

    def save_moderator_vote(self, chat_id: int, voter_id: int, moderator_id: int, vote_date: str) -> None:
        now = utc_now()
        self._conn.execute(
            """
            insert into chat_moderator_votes (chat_id, voter_id, moderator_id, vote_date, created_at, updated_at)
            values (?, ?, ?, ?, ?, ?)
            on conflict(chat_id, voter_id) do update set
                moderator_id = excluded.moderator_id,
                vote_date = excluded.vote_date,
                updated_at = excluded.updated_at
            """,
            (chat_id, voter_id, moderator_id, vote_date, now, now),
        )
        self._conn.commit()

    def moderator_vote_for_user(self, chat_id: int, voter_id: int) -> dict | None:
        row = self._conn.execute(
            """
            select chat_id, voter_id, moderator_id, vote_date, created_at, updated_at
            from chat_moderator_votes
            where chat_id = ? and voter_id = ?
            """,
            (chat_id, voter_id),
        ).fetchone()
        return dict(row) if row else None

    def set_chat_lock(
        self,
        chat_id: int,
        enabled: bool,
        updated_by: int | None,
        reason: str = "",
        until_at: str | None = None,
    ) -> None:
        self._conn.execute(
            """
            insert into chat_lock_settings (chat_id, enabled, reason, until_at, updated_by, updated_at)
            values (?, ?, ?, ?, ?, ?)
            on conflict(chat_id) do update set
                enabled = excluded.enabled,
                reason = excluded.reason,
                until_at = excluded.until_at,
                updated_by = excluded.updated_by,
                updated_at = excluded.updated_at
            """,
            (chat_id, int(enabled), reason.strip()[:500], until_at, updated_by, utc_now()),
        )
        self._conn.commit()

    def get_chat_lock(self, chat_id: int, now: str | None = None) -> dict | None:
        check_at = now or utc_now()
        row = self._conn.execute(
            """
            select chat_id, enabled, reason, until_at, updated_by, updated_at
            from chat_lock_settings
            where chat_id = ? and enabled = 1
              and (until_at is null or until_at > ?)
            """,
            (chat_id, check_at),
        ).fetchone()
        return dict(row) if row else None

    @staticmethod
    def _social_pair(user1_id: int, user2_id: int) -> tuple[int, int]:
        return (user1_id, user2_id) if user1_id < user2_id else (user2_id, user1_id)

    def friendship_state(self, chat_id: int, user_id: int, other_id: int) -> str:
        if user_id == other_id:
            return "self"
        user1_id, user2_id = self._social_pair(user_id, other_id)
        row = self._conn.execute(
            """
            select 1 from chat_friendships
            where chat_id = ? and user1_id = ? and user2_id = ?
            """,
            (chat_id, user1_id, user2_id),
        ).fetchone()
        if row:
            return "friends"
        row = self._conn.execute(
            """
            select requester_id, target_id from chat_friend_requests
            where chat_id = ? and (
                (requester_id = ? and target_id = ?)
                or (requester_id = ? and target_id = ?)
            )
            limit 1
            """,
            (chat_id, user_id, other_id, other_id, user_id),
        ).fetchone()
        if not row:
            return "none"
        return "outgoing" if int(row["requester_id"]) == user_id else "incoming"

    def create_friend_request(self, chat_id: int, requester_id: int, target_id: int) -> str:
        state = self.friendship_state(chat_id, requester_id, target_id)
        if state != "none":
            return state
        self._conn.execute(
            """
            insert into chat_friend_requests (chat_id, requester_id, target_id, created_at)
            values (?, ?, ?, ?)
            """,
            (chat_id, requester_id, target_id, utc_now()),
        )
        self._conn.commit()
        return "created"

    def accept_friend_request(self, chat_id: int, requester_id: int, target_id: int) -> bool:
        row = self._conn.execute(
            """
            select 1 from chat_friend_requests
            where chat_id = ? and requester_id = ? and target_id = ?
            """,
            (chat_id, requester_id, target_id),
        ).fetchone()
        if not row:
            return False
        user1_id, user2_id = self._social_pair(requester_id, target_id)
        self._conn.execute(
            """
            insert or ignore into chat_friendships (chat_id, user1_id, user2_id, created_at)
            values (?, ?, ?, ?)
            """,
            (chat_id, user1_id, user2_id, utc_now()),
        )
        self._conn.execute(
            """
            delete from chat_friend_requests
            where chat_id = ? and (
                (requester_id = ? and target_id = ?)
                or (requester_id = ? and target_id = ?)
            )
            """,
            (chat_id, requester_id, target_id, target_id, requester_id),
        )
        self._conn.commit()
        return True

    def decline_friend_request(self, chat_id: int, requester_id: int, target_id: int) -> bool:
        cur = self._conn.execute(
            """
            delete from chat_friend_requests
            where chat_id = ? and requester_id = ? and target_id = ?
            """,
            (chat_id, requester_id, target_id),
        )
        self._conn.commit()
        return cur.rowcount > 0

    def remove_friendship(self, chat_id: int, user_id: int, other_id: int) -> bool:
        user1_id, user2_id = self._social_pair(user_id, other_id)
        cur = self._conn.execute(
            """
            delete from chat_friendships
            where chat_id = ? and user1_id = ? and user2_id = ?
            """,
            (chat_id, user1_id, user2_id),
        )
        self._conn.commit()
        return cur.rowcount > 0

    def list_chat_friends(self, chat_id: int, user_id: int, limit: int = 20) -> list[SeenUser]:
        rows = self._conn.execute(
            """
            select u.chat_id, u.user_id, u.username, u.full_name, u.is_bot, u.updated_at
            from chat_friendships f
            join seen_users u
              on u.chat_id = f.chat_id
             and u.user_id = case when f.user1_id = ? then f.user2_id else f.user1_id end
            where f.chat_id = ? and (f.user1_id = ? or f.user2_id = ?)
            order by u.full_name collate nocase
            limit ?
            """,
            (user_id, chat_id, user_id, user_id, max(1, limit)),
        ).fetchall()
        return [SeenUser(**dict(row)) for row in rows]

    def list_registered_social_gift_friends(self, user_id: int, limit: int = 50) -> list[SocialGiftRecipient]:
        rows = self._conn.execute(
            """
            select
                u.user_id,
                coalesce(max(nullif(u.username, '')), '') as username,
                coalesce(max(nullif(u.full_name, '')), 'Игрок') as full_name,
                'friend' as relation,
                count(distinct f.chat_id) as chat_count,
                max(u.updated_at) as updated_at
            from chat_friendships f
            join seen_users u
              on u.chat_id = f.chat_id
             and u.user_id = case when f.user1_id = ? then f.user2_id else f.user1_id end
            join dig_players p on p.chat_id = ? and p.user_id = u.user_id
            where (f.user1_id = ? or f.user2_id = ?) and u.user_id != ? and coalesce(u.is_bot, 0) = 0
            group by u.user_id
            order by lower(coalesce(max(nullif(u.full_name, '')), 'Игрок'))
            limit ?
            """,
            (user_id, DIG_GLOBAL_CHAT_ID, user_id, user_id, user_id, max(1, limit)),
        ).fetchall()
        return [
            SocialGiftRecipient(
                user_id=int(row["user_id"]),
                username=(row["username"] or None),
                full_name=row["full_name"],
                relation=row["relation"],
                chat_count=int(row["chat_count"]),
                updated_at=row["updated_at"],
            )
            for row in rows
        ]

    def list_social_friends(self, user_id: int, limit: int = 80) -> list[SocialGiftRecipient]:
        rows = self._conn.execute(
            """
            select
                u.user_id,
                coalesce(max(nullif(u.username, '')), '') as username,
                coalesce(max(nullif(u.full_name, '')), 'Игрок') as full_name,
                'friend' as relation,
                count(distinct f.chat_id) as chat_count,
                max(u.updated_at) as updated_at
            from chat_friendships f
            join seen_users u
              on u.chat_id = f.chat_id
             and u.user_id = case when f.user1_id = ? then f.user2_id else f.user1_id end
            where (f.user1_id = ? or f.user2_id = ?) and u.user_id != ? and coalesce(u.is_bot, 0) = 0
            group by u.user_id
            order by lower(coalesce(max(nullif(u.full_name, '')), 'Игрок'))
            limit ?
            """,
            (user_id, user_id, user_id, user_id, max(1, limit)),
        ).fetchall()
        return [
            SocialGiftRecipient(
                user_id=int(row["user_id"]),
                username=(row["username"] or None),
                full_name=row["full_name"],
                relation=row["relation"],
                chat_count=int(row["chat_count"]),
                updated_at=row["updated_at"],
            )
            for row in rows
        ]

    def count_chat_friends(self, chat_id: int, user_id: int) -> int:
        row = self._conn.execute(
            """
            select count(*) as total from chat_friendships
            where chat_id = ? and (user1_id = ? or user2_id = ?)
            """,
            (chat_id, user_id, user_id),
        ).fetchone()
        return int(row["total"]) if row else 0

    def get_chat_couple(self, chat_id: int, user_id: int) -> ChatCouple | None:
        row = self._conn.execute(
            """
            select chat_id, user1_id, user2_id, created_at
            from chat_couples
            where chat_id = ? and (user1_id = ? or user2_id = ?)
            limit 1
            """,
            (chat_id, user_id, user_id),
        ).fetchone()
        return ChatCouple(**dict(row)) if row else None

    def get_chat_partner(self, chat_id: int, user_id: int) -> SeenUser | None:
        row = self._conn.execute(
            """
            select u.chat_id, u.user_id, u.username, u.full_name, u.is_bot, u.updated_at
            from chat_couples c
            join seen_users u
              on u.chat_id = c.chat_id
             and u.user_id = case when c.user1_id = ? then c.user2_id else c.user1_id end
            where c.chat_id = ? and (c.user1_id = ? or c.user2_id = ?)
            limit 1
            """,
            (user_id, chat_id, user_id, user_id),
        ).fetchone()
        return SeenUser(**dict(row)) if row else None

    def list_registered_social_gift_partners(self, user_id: int, limit: int = 20) -> list[SocialGiftRecipient]:
        rows = self._conn.execute(
            """
            select
                u.user_id,
                coalesce(max(nullif(u.username, '')), '') as username,
                coalesce(max(nullif(u.full_name, '')), 'Игрок') as full_name,
                'partner' as relation,
                count(distinct c.chat_id) as chat_count,
                max(u.updated_at) as updated_at
            from chat_couples c
            join seen_users u
              on u.chat_id = c.chat_id
             and u.user_id = case when c.user1_id = ? then c.user2_id else c.user1_id end
            join dig_players p on p.chat_id = ? and p.user_id = u.user_id
            where (c.user1_id = ? or c.user2_id = ?) and u.user_id != ? and coalesce(u.is_bot, 0) = 0
            group by u.user_id
            order by lower(coalesce(max(nullif(u.full_name, '')), 'Игрок'))
            limit ?
            """,
            (user_id, DIG_GLOBAL_CHAT_ID, user_id, user_id, user_id, max(1, limit)),
        ).fetchall()
        return [
            SocialGiftRecipient(
                user_id=int(row["user_id"]),
                username=(row["username"] or None),
                full_name=row["full_name"],
                relation=row["relation"],
                chat_count=int(row["chat_count"]),
                updated_at=row["updated_at"],
            )
            for row in rows
        ]

    def list_social_partners(self, user_id: int, limit: int = 20) -> list[SocialGiftRecipient]:
        rows = self._conn.execute(
            """
            select
                u.user_id,
                coalesce(max(nullif(u.username, '')), '') as username,
                coalesce(max(nullif(u.full_name, '')), 'Игрок') as full_name,
                'partner' as relation,
                count(distinct c.chat_id) as chat_count,
                max(u.updated_at) as updated_at
            from chat_couples c
            join seen_users u
              on u.chat_id = c.chat_id
             and u.user_id = case when c.user1_id = ? then c.user2_id else c.user1_id end
            where (c.user1_id = ? or c.user2_id = ?) and u.user_id != ? and coalesce(u.is_bot, 0) = 0
            group by u.user_id
            order by lower(coalesce(max(nullif(u.full_name, '')), 'Игрок'))
            limit ?
            """,
            (user_id, user_id, user_id, user_id, max(1, limit)),
        ).fetchall()
        return [
            SocialGiftRecipient(
                user_id=int(row["user_id"]),
                username=(row["username"] or None),
                full_name=row["full_name"],
                relation=row["relation"],
                chat_count=int(row["chat_count"]),
                updated_at=row["updated_at"],
            )
            for row in rows
        ]

    def get_known_user(self, user_id: int) -> SeenUser | None:
        row = self._conn.execute(
            """
            select
                u.chat_id,
                u.user_id,
                coalesce(max(nullif(u.username, '')), '') as username,
                coalesce(max(nullif(u.full_name, '')), 'Игрок') as full_name,
                min(coalesce(u.is_bot, 0)) as is_bot,
                max(u.updated_at) as updated_at
            from seen_users u
            where u.user_id = ? and coalesce(u.is_bot, 0) = 0
            group by u.user_id
            limit 1
            """,
            (user_id,),
        ).fetchone()
        if not row:
            return None
        data = dict(row)
        data["username"] = data["username"] or None
        return SeenUser(**data)

    def couple_state(self, chat_id: int, user_id: int, other_id: int) -> str:
        if user_id == other_id:
            return "self"
        couple = self.get_chat_couple(chat_id, user_id)
        if couple:
            partner_id = couple.user2_id if couple.user1_id == user_id else couple.user1_id
            return "couple" if partner_id == other_id else "user_busy"
        if self.get_chat_couple(chat_id, other_id):
            return "target_busy"
        row = self._conn.execute(
            """
            select requester_id, target_id from chat_couple_requests
            where chat_id = ? and (
                (requester_id = ? and target_id = ?)
                or (requester_id = ? and target_id = ?)
            )
            limit 1
            """,
            (chat_id, user_id, other_id, other_id, user_id),
        ).fetchone()
        if not row:
            return "none"
        return "outgoing" if int(row["requester_id"]) == user_id else "incoming"

    def create_couple_request(self, chat_id: int, requester_id: int, target_id: int) -> str:
        state = self.couple_state(chat_id, requester_id, target_id)
        if state != "none":
            return state
        self._conn.execute(
            """
            insert into chat_couple_requests (chat_id, requester_id, target_id, created_at)
            values (?, ?, ?, ?)
            """,
            (chat_id, requester_id, target_id, utc_now()),
        )
        self._conn.commit()
        return "created"

    def accept_couple_request(self, chat_id: int, requester_id: int, target_id: int) -> str:
        row = self._conn.execute(
            """
            select 1 from chat_couple_requests
            where chat_id = ? and requester_id = ? and target_id = ?
            """,
            (chat_id, requester_id, target_id),
        ).fetchone()
        if not row:
            return "missing"
        if self.get_chat_couple(chat_id, requester_id) or self.get_chat_couple(chat_id, target_id):
            return "busy"
        user1_id, user2_id = self._social_pair(requester_id, target_id)
        self._conn.execute(
            """
            insert into chat_couples (chat_id, user1_id, user2_id, created_at)
            values (?, ?, ?, ?)
            """,
            (chat_id, user1_id, user2_id, utc_now()),
        )
        self._conn.execute(
            """
            insert or ignore into chat_friendships (chat_id, user1_id, user2_id, created_at)
            values (?, ?, ?, ?)
            """,
            (chat_id, user1_id, user2_id, utc_now()),
        )
        self._conn.execute(
            """
            delete from chat_couple_requests
            where chat_id = ? and (
                requester_id in (?, ?) or target_id in (?, ?)
            )
            """,
            (chat_id, requester_id, target_id, requester_id, target_id),
        )
        self._conn.commit()
        return "accepted"

    def decline_couple_request(self, chat_id: int, requester_id: int, target_id: int) -> bool:
        cur = self._conn.execute(
            """
            delete from chat_couple_requests
            where chat_id = ? and requester_id = ? and target_id = ?
            """,
            (chat_id, requester_id, target_id),
        )
        self._conn.commit()
        return cur.rowcount > 0

    def end_chat_couple(self, chat_id: int, user_id: int, partner_id: int) -> bool:
        user1_id, user2_id = self._social_pair(user_id, partner_id)
        cur = self._conn.execute(
            """
            delete from chat_couples
            where chat_id = ? and user1_id = ? and user2_id = ?
            """,
            (chat_id, user1_id, user2_id),
        )
        self._conn.commit()
        return cur.rowcount > 0

    def get_daily_pick(self, chat_id: int, pick_key: str, pick_date: str) -> SeenUser | None:
        row = self._conn.execute(
            """
            select u.chat_id, u.user_id, u.username, u.full_name, u.is_bot, u.updated_at
            from daily_picks p
            join seen_users u on u.chat_id = p.chat_id and u.user_id = p.user_id
            where p.chat_id = ? and p.pick_key = ? and p.pick_date = ?
            """,
            (chat_id, pick_key, pick_date),
        ).fetchone()
        return SeenUser(**dict(row)) if row else None

    def set_daily_pick(self, chat_id: int, pick_key: str, pick_date: str, user_id: int) -> None:
        self._conn.execute(
            """
            insert or replace into daily_picks (chat_id, pick_key, pick_date, user_id, created_at)
            values (?, ?, ?, ?, ?)
            """,
            (chat_id, pick_key, pick_date, user_id, utc_now()),
        )
        self._conn.commit()

    def upsert_topic(self, chat_id: int, thread_id: int, title: str, preserve_existing: bool = False) -> None:
        if preserve_existing:
            existing = self._conn.execute(
                "select 1 from chat_topics where chat_id = ? and thread_id = ?",
                (chat_id, thread_id),
            ).fetchone()
            if existing:
                return
        title = re.sub(rf"\s*#{thread_id}\s*$", "", title).strip() or "Без названия"
        self._conn.execute(
            """
            insert into chat_topics (chat_id, thread_id, title, updated_at)
            values (?, ?, ?, ?)
            on conflict(chat_id, thread_id) do update set
                title = excluded.title,
                updated_at = excluded.updated_at
            """,
            (chat_id, thread_id, title, utc_now()),
        )
        self._conn.commit()

    def list_topics(self, chat_id: int) -> list[ChatTopic]:
        rows = self._conn.execute(
            """
            select chat_id, thread_id, title, updated_at
            from chat_topics
            where chat_id = ?
            order by updated_at desc
            """,
            (chat_id,),
        ).fetchall()
        return [ChatTopic(**dict(row)) for row in rows]

    def delete_topics(self, chat_id: int) -> None:
        self._conn.execute("delete from chat_topics where chat_id = ?", (chat_id,))
        self._conn.commit()

    def add_audit_log(
        self,
        source: str,
        action: str,
        *,
        chat_id: int | None = None,
        actor_id: int | None = None,
        actor_username: str | None = None,
        actor_name: str = "",
        details: str = "",
    ) -> int:
        cur = self._conn.execute(
            """
            insert into audit_logs
                (chat_id, actor_id, actor_username, actor_name, source, action, details, created_at)
            values (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (chat_id, actor_id, actor_username, actor_name, source, action, details[:1000], utc_now()),
        )
        self._conn.commit()
        return int(cur.lastrowid)

    def list_audit_logs(self, chat_id: int | None = None, limit: int = 100) -> list[AuditLog]:
        safe_limit = max(1, min(500, int(limit)))
        if chat_id is None:
            rows = self._conn.execute(
                """
                select id, chat_id, actor_id, actor_username, actor_name, source, action, details, created_at
                from audit_logs order by id desc limit ?
                """,
                (safe_limit,),
            ).fetchall()
        else:
            rows = self._conn.execute(
                """
                select id, chat_id, actor_id, actor_username, actor_name, source, action, details, created_at
                from audit_logs where chat_id = ? order by id desc limit ?
                """,
                (chat_id, safe_limit),
            ).fetchall()
        return [AuditLog(**dict(row)) for row in rows]

    def add_device_event(
        self,
        *,
        app: str,
        event_type: str,
        event_name: str,
        user_id: int | None = None,
        device_id: str | None = None,
        app_version: str | None = None,
        android_version: str | None = None,
        sdk: int | None = None,
        manufacturer: str | None = None,
        model: str | None = None,
        screen: str | None = None,
        density: str | None = None,
        locale: str | None = None,
        timezone: str | None = None,
        network_type: str | None = None,
        endpoint: str | None = None,
        status_code: int | None = None,
        duration_ms: int | None = None,
        error_type: str | None = None,
        message: str | None = None,
        metadata: dict | None = None,
    ) -> int:
        cur = self._conn.execute(
            """
            insert into device_events (
                app, event_type, event_name, user_id, device_id, app_version,
                android_version, sdk, manufacturer, model, screen, density,
                locale, timezone, network_type, endpoint, status_code, duration_ms,
                error_type, message, metadata_json, created_at
            )
            values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                app[:64],
                event_type[:64],
                event_name[:128],
                user_id,
                (device_id or "")[:128] or None,
                (app_version or "")[:64] or None,
                (android_version or "")[:64] or None,
                sdk,
                (manufacturer or "")[:80] or None,
                (model or "")[:120] or None,
                (screen or "")[:64] or None,
                (density or "")[:64] or None,
                (locale or "")[:32] or None,
                (timezone or "")[:80] or None,
                (network_type or "")[:32] or None,
                (endpoint or "")[:200] or None,
                status_code,
                duration_ms,
                (error_type or "")[:80] or None,
                (message or "")[:500] or None,
                json.dumps(metadata or {}, ensure_ascii=False)[:4000],
                utc_now(),
            ),
        )
        self._conn.commit()
        return int(cur.lastrowid)

    def list_device_events(self, limit: int = 100, app: str | None = None, event_type: str | None = None) -> list[dict]:
        safe_limit = max(1, min(500, int(limit)))
        clauses: list[str] = []
        params: list[object] = []
        if app:
            clauses.append("app = ?")
            params.append(app[:64])
        if event_type:
            clauses.append("event_type = ?")
            params.append(event_type[:64])
        where = (" where " + " and ".join(clauses)) if clauses else ""
        rows = self._conn.execute(
            f"""
            select id, app, event_type, event_name, user_id, device_id, app_version,
                   android_version, sdk, manufacturer, model, screen, density,
                   locale, timezone, network_type, endpoint, status_code, duration_ms,
                   error_type, message, metadata_json, created_at
            from device_events{where}
            order by id desc limit ?
            """,
            (*params, safe_limit),
        ).fetchall()
        items = []
        for row in rows:
            item = dict(row)
            try:
                item["metadata"] = json.loads(item.pop("metadata_json") or "{}")
            except json.JSONDecodeError:
                item["metadata"] = {}
            items.append(item)
        return items

    def device_events_summary(self) -> dict:
        by_app = [
            dict(row)
            for row in self._conn.execute(
                "select app, count(*) as total from device_events group by app order by total desc"
            ).fetchall()
        ]
        by_type = [
            dict(row)
            for row in self._conn.execute(
                "select event_type, count(*) as total from device_events group by event_type order by total desc"
            ).fetchall()
        ]
        errors = [
            dict(row)
            for row in self._conn.execute(
                """
                select app, endpoint, error_type, count(*) as total, max(created_at) as last_at
                from device_events
                where event_type = 'error'
                group by app, endpoint, error_type
                order by total desc, last_at desc
                limit 20
                """
            ).fetchall()
        ]
        devices = self._conn.execute(
            "select count(distinct coalesce(device_id, app || ':' || ifnull(user_id, 'anonymous'))) as total from device_events"
        ).fetchone()
        return {
            "total": int(self._conn.execute("select count(*) as total from device_events").fetchone()["total"]),
            "devices": int(devices["total"] if devices else 0),
            "byApp": by_app,
            "byType": by_type,
            "topErrors": errors,
        }

    def get_giveaway_settings(self, chat_id: int) -> GiveawaySettings:
        row = self._conn.execute(
            """
            select chat_id, trigger, title, winners_count, updated_by, updated_at
            from giveaway_settings
            where chat_id = ?
            """,
            (chat_id,),
        ).fetchone()
        if row:
            return GiveawaySettings(**dict(row))

        return GiveawaySettings(
            chat_id=chat_id,
            trigger=normalize_trigger("кто пидор"),
            title="Пидор дня",
            winners_count=1,
            updated_by=None,
            updated_at=utc_now(),
        )

    def set_giveaway_settings(
        self,
        chat_id: int,
        trigger: str,
        title: str,
        winners_count: int,
        updated_by: int | None,
    ) -> None:
        count = max(1, min(20, int(winners_count)))
        self._conn.execute(
            """
            insert into giveaway_settings (chat_id, trigger, title, winners_count, updated_by, updated_at)
            values (?, ?, ?, ?, ?, ?)
            on conflict(chat_id) do update set
                trigger = excluded.trigger,
                title = excluded.title,
                winners_count = excluded.winners_count,
                updated_by = excluded.updated_by,
                updated_at = excluded.updated_at
            """,
            (chat_id, normalize_trigger(trigger), title.strip(), count, updated_by, utc_now()),
        )
        self._conn.commit()

    def get_giveaway_picks(self, chat_id: int, pick_key: str, pick_date: str) -> list[SeenUser]:
        rows = self._conn.execute(
            """
            select u.chat_id, u.user_id, u.username, u.full_name, u.is_bot, u.updated_at
            from giveaway_daily_picks p
            join seen_users u on u.chat_id = p.chat_id and u.user_id = p.user_id
            where p.chat_id = ? and p.pick_key = ? and p.pick_date = ?
            order by p.pick_rank
            """,
            (chat_id, pick_key, pick_date),
        ).fetchall()
        return [SeenUser(**dict(row)) for row in rows]

    def set_giveaway_picks(self, chat_id: int, pick_key: str, pick_date: str, user_ids: list[int]) -> None:
        self._conn.execute(
            "delete from giveaway_daily_picks where chat_id = ? and pick_key = ? and pick_date = ?",
            (chat_id, pick_key, pick_date),
        )
        for index, user_id in enumerate(user_ids, start=1):
            self._conn.execute(
                """
                insert into giveaway_daily_picks (chat_id, pick_key, pick_date, pick_rank, user_id, created_at)
                values (?, ?, ?, ?, ?, ?)
                """,
                (chat_id, pick_key, pick_date, index, user_id, utc_now()),
            )
        self._conn.commit()

    def increment_giveaway_stats(self, chat_id: int, user_ids: list[int]) -> None:
        for user_id in user_ids:
            self._conn.execute(
                """
                insert into giveaway_stats (chat_id, user_id, wins_count, updated_at)
                values (?, ?, 1, ?)
                on conflict(chat_id, user_id) do update set
                    wins_count = wins_count + 1,
                    updated_at = excluded.updated_at
                """,
                (chat_id, user_id, utc_now()),
            )
        self._conn.commit()

    def award_giveaway_stats_once(self, chat_id: int, pick_key: str, pick_date: str, user_ids: list[int]) -> bool:
        cur = self._conn.execute(
            """
            insert or ignore into giveaway_stat_awards (chat_id, pick_key, pick_date, created_at)
            values (?, ?, ?, ?)
            """,
            (chat_id, pick_key, pick_date, utc_now()),
        )
        if cur.rowcount == 0:
            self._conn.commit()
            return False

        for user_id in user_ids:
            self._conn.execute(
                """
                insert into giveaway_stats (chat_id, user_id, wins_count, updated_at)
                values (?, ?, 1, ?)
                on conflict(chat_id, user_id) do update set
                    wins_count = wins_count + 1,
                    updated_at = excluded.updated_at
                """,
                (chat_id, user_id, utc_now()),
            )
        self._conn.commit()
        return True

    def top_giveaway_stats(self, chat_id: int, limit: int | None = 10) -> list[GiveawayStat]:
        query = """
            select
                s.chat_id,
                s.user_id,
                u.username,
                coalesce(u.full_name, cast(s.user_id as text)) as full_name,
                s.wins_count
            from giveaway_stats s
            left join seen_users u on u.chat_id = s.chat_id and u.user_id = s.user_id
            where s.chat_id = ?
            order by s.wins_count desc, u.username collate nocase
        """
        params: tuple = (chat_id,)
        if limit is not None:
            query += " limit ?"
            params = (chat_id, limit)
        rows = self._conn.execute(query, params).fetchall()
        return [GiveawayStat(**dict(row)) for row in rows]

    def get_alarm_settings(self, chat_id: int) -> AlarmSettings:
        row = self._conn.execute(
            """
            select chat_id, enabled, permissions_json, reactions_json, alarm_text, clear_text, alarm_thread_id, updated_by, updated_at
            from alarm_settings
            where chat_id = ?
            """,
            (chat_id,),
        ).fetchone()
        if row:
            return AlarmSettings(**dict(row))
        return AlarmSettings(
            chat_id=chat_id,
            enabled=0,
            permissions_json=None,
            reactions_json=None,
            alarm_text=None,
            clear_text=None,
            alarm_thread_id=None,
            updated_by=None,
            updated_at=utc_now(),
        )

    def set_alarm_thread(self, chat_id: int, thread_id: int | None, updated_by: int | None) -> None:
        current = self.get_alarm_settings(chat_id)
        self._conn.execute(
            """
            insert into alarm_settings (
                chat_id, enabled, permissions_json, reactions_json, alarm_text,
                clear_text, alarm_thread_id, updated_by, updated_at
            )
            values (?, ?, ?, ?, ?, ?, ?, ?, ?)
            on conflict(chat_id) do update set
                alarm_thread_id = excluded.alarm_thread_id,
                updated_by = excluded.updated_by,
                updated_at = excluded.updated_at
            """,
            (
                chat_id,
                current.enabled,
                current.permissions_json,
                current.reactions_json,
                current.alarm_text,
                current.clear_text,
                thread_id,
                updated_by,
                utc_now(),
            ),
        )
        self._conn.commit()

    def set_alarm_enabled(self, chat_id: int, enabled: bool, updated_by: int | None) -> None:
        current = self.get_alarm_settings(chat_id)
        self._conn.execute(
            """
            insert into alarm_settings (chat_id, enabled, permissions_json, reactions_json, alarm_text, clear_text, updated_by, updated_at)
            values (?, ?, ?, ?, ?, ?, ?, ?)
            on conflict(chat_id) do update set
                enabled = excluded.enabled,
                updated_by = excluded.updated_by,
                updated_at = excluded.updated_at
            """,
            (
                chat_id,
                int(enabled),
                current.permissions_json,
                current.reactions_json,
                current.alarm_text,
                current.clear_text,
                updated_by,
                utc_now(),
            ),
        )
        self._conn.commit()

    def set_alarm_texts(
        self,
        chat_id: int,
        alarm_text: str | None = None,
        clear_text: str | None = None,
        updated_by: int | None = None,
    ) -> None:
        current = self.get_alarm_settings(chat_id)
        self._conn.execute(
            """
            insert into alarm_settings (chat_id, enabled, permissions_json, reactions_json, alarm_text, clear_text, updated_by, updated_at)
            values (?, ?, ?, ?, ?, ?, ?, ?)
            on conflict(chat_id) do update set
                alarm_text = excluded.alarm_text,
                clear_text = excluded.clear_text,
                updated_by = excluded.updated_by,
                updated_at = excluded.updated_at
            """,
            (
                chat_id,
                current.enabled,
                current.permissions_json,
                current.reactions_json,
                alarm_text if alarm_text is not None else current.alarm_text,
                clear_text if clear_text is not None else current.clear_text,
                updated_by,
                utc_now(),
            ),
        )
        self._conn.commit()

    def save_alarm_permissions(self, chat_id: int, permissions: dict) -> None:
        current = self.get_alarm_settings(chat_id)
        self._conn.execute(
            """
            insert into alarm_settings (chat_id, enabled, permissions_json, reactions_json, alarm_text, clear_text, updated_by, updated_at)
            values (?, ?, ?, ?, ?, ?, ?, ?)
            on conflict(chat_id) do update set
                permissions_json = excluded.permissions_json,
                updated_at = excluded.updated_at
            """,
            (
                chat_id,
                current.enabled,
                json.dumps(permissions, ensure_ascii=False),
                current.reactions_json,
                current.alarm_text,
                current.clear_text,
                current.updated_by,
                utc_now(),
            ),
        )
        self._conn.commit()

    def save_alarm_reactions(self, chat_id: int, reactions: list | None) -> None:
        current = self.get_alarm_settings(chat_id)
        self._conn.execute(
            """
            insert into alarm_settings (chat_id, enabled, permissions_json, reactions_json, alarm_text, clear_text, updated_by, updated_at)
            values (?, ?, ?, ?, ?, ?, ?, ?)
            on conflict(chat_id) do update set
                reactions_json = excluded.reactions_json,
                updated_at = excluded.updated_at
            """,
            (
                chat_id,
                current.enabled,
                current.permissions_json,
                json.dumps(reactions, ensure_ascii=False) if reactions is not None else None,
                current.alarm_text,
                current.clear_text,
                current.updated_by,
                utc_now(),
            ),
        )
        self._conn.commit()

    def pop_alarm_reactions(self, chat_id: int) -> list | None:
        current = self.get_alarm_settings(chat_id)
        if current.reactions_json is None:
            return None
        self._conn.execute(
            "update alarm_settings set reactions_json = null, updated_at = ? where chat_id = ?",
            (utc_now(), chat_id),
        )
        self._conn.commit()
        return json.loads(current.reactions_json)

    def pop_alarm_permissions(self, chat_id: int) -> dict | None:
        current = self.get_alarm_settings(chat_id)
        if not current.permissions_json:
            return None
        self._conn.execute(
            "update alarm_settings set permissions_json = null, updated_at = ? where chat_id = ?",
            (utc_now(), chat_id),
        )
        self._conn.commit()
        return json.loads(current.permissions_json)

    def alarm_api_enabled(self, chat_id: int) -> bool:
        row = self._conn.execute(
            "select enabled from alarm_api_settings where chat_id = ?",
            (chat_id,),
        ).fetchone()
        return bool(row["enabled"]) if row else False

    def set_alarm_api_enabled(self, chat_id: int, enabled: bool, updated_by: int | None) -> None:
        self._conn.execute(
            """
            insert into alarm_api_settings (
                chat_id, enabled, last_status, last_notified_status,
                last_alarm_message_id, last_clear_message_id,
                last_alarm_action_message_id, last_clear_action_message_id,
                updated_by, updated_at
            )
            values (?, ?, null, null, null, null, null, null, ?, ?)
            on conflict(chat_id) do update set
                enabled = excluded.enabled,
                last_status = null,
                last_notified_status = null,
                last_alarm_message_id = null,
                last_clear_message_id = null,
                last_alarm_action_message_id = null,
                last_clear_action_message_id = null,
                updated_by = excluded.updated_by,
                updated_at = excluded.updated_at
            """,
            (chat_id, int(enabled), updated_by, utc_now()),
        )
        self._conn.commit()

    def list_alarm_api_chats(self) -> list[int]:
        rows = self._conn.execute(
            "select chat_id from alarm_api_settings where enabled = 1 order by chat_id"
        ).fetchall()
        return [int(row["chat_id"]) for row in rows]

    def alarm_api_last_status(self, chat_id: int) -> str | None:
        row = self._conn.execute(
            "select last_status from alarm_api_settings where chat_id = ? and enabled = 1",
            (chat_id,),
        ).fetchone()
        return row["last_status"] if row else None

    def set_alarm_api_last_status(self, chat_id: int, status: str) -> None:
        self._conn.execute(
            "update alarm_api_settings set last_status = ?, updated_at = ? where chat_id = ? and enabled = 1",
            (status, utc_now(), chat_id),
        )
        self._conn.commit()

    def alarm_api_last_notified_status(self, chat_id: int) -> str | None:
        row = self._conn.execute(
            "select last_notified_status from alarm_api_settings where chat_id = ? and enabled = 1",
            (chat_id,),
        ).fetchone()
        return row["last_notified_status"] if row else None

    def set_alarm_api_last_notified_status(self, chat_id: int, status: str) -> None:
        self._conn.execute(
            "update alarm_api_settings set last_notified_status = ?, updated_at = ? where chat_id = ? and enabled = 1",
            (status, utc_now(), chat_id),
        )
        self._conn.commit()

    def alarm_api_status_message_id(self, chat_id: int, status: str) -> int | None:
        column = "last_alarm_message_id" if status in {"A", "P"} else "last_clear_message_id"
        row = self._conn.execute(
            f"select {column} from alarm_api_settings where chat_id = ? and enabled = 1",
            (chat_id,),
        ).fetchone()
        return int(row[column]) if row and row[column] is not None else None

    def set_alarm_api_status_message_id(self, chat_id: int, status: str, message_id: int | None) -> None:
        column = "last_alarm_message_id" if status in {"A", "P"} else "last_clear_message_id"
        self._conn.execute(
            f"update alarm_api_settings set {column} = ?, updated_at = ? where chat_id = ? and enabled = 1",
            (message_id, utc_now(), chat_id),
        )
        self._conn.commit()

    def alarm_api_status_message_ids(self, chat_id: int, status: str) -> list[int]:
        if status in {"A", "P"}:
            columns = ("last_alarm_message_id", "last_alarm_action_message_id")
        else:
            columns = ("last_clear_message_id", "last_clear_action_message_id")
        row = self._conn.execute(
            f"select {columns[0]}, {columns[1]} from alarm_api_settings where chat_id = ? and enabled = 1",
            (chat_id,),
        ).fetchone()
        if not row:
            return []
        return [int(row[column]) for column in columns if row[column] is not None]

    def set_alarm_api_action_message_id(self, chat_id: int, status: str, message_id: int | None) -> None:
        column = "last_alarm_action_message_id" if status in {"A", "P"} else "last_clear_action_message_id"
        self._conn.execute(
            f"update alarm_api_settings set {column} = ?, updated_at = ? where chat_id = ? and enabled = 1",
            (message_id, utc_now(), chat_id),
        )
        self._conn.commit()

    def clear_alarm_api_status_message_ids(self, chat_id: int, status: str) -> None:
        if status in {"A", "P"}:
            columns = ("last_alarm_message_id", "last_alarm_action_message_id")
        else:
            columns = ("last_clear_message_id", "last_clear_action_message_id")
        self._conn.execute(
            f"update alarm_api_settings set {columns[0]} = null, {columns[1]} = null, updated_at = ? where chat_id = ? and enabled = 1",
            (utc_now(), chat_id),
        )
        self._conn.commit()

    def alarm_restrictions_enabled(self, chat_id: int) -> bool:
        row = self._conn.execute(
            "select enabled from alarm_restriction_settings where chat_id = ?",
            (chat_id,),
        ).fetchone()
        return bool(row["enabled"]) if row else True

    def set_alarm_restrictions_enabled(self, chat_id: int, enabled: bool, updated_by: int | None) -> None:
        self._conn.execute(
            """
            insert into alarm_restriction_settings (chat_id, enabled, updated_by, updated_at)
            values (?, ?, ?, ?)
            on conflict(chat_id) do update set
                enabled = excluded.enabled,
                updated_by = excluded.updated_by,
                updated_at = excluded.updated_at
            """,
            (chat_id, int(enabled), updated_by, utc_now()),
        )
        self._conn.commit()

    def add_star_payment(
        self,
        user_id: int,
        username: str | None,
        full_name: str,
        chat_id: int | None,
        amount: int,
        currency: str,
        charge_id: str,
    ) -> bool:
        cur = self._conn.execute(
            """
            insert or ignore into star_payments (user_id, username, full_name, chat_id, amount, currency, charge_id, created_at)
            values (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (user_id, normalize_username(username) if username else None, full_name, chat_id, amount, currency, charge_id, utc_now()),
        )
        self._conn.commit()
        return cur.rowcount > 0

    def apply_dig_star_purchase_once(
        self,
        *,
        user_id: int,
        username: str | None,
        full_name: str,
        chat_id: int,
        amount: int,
        currency: str,
        charge_id: str,
        action: str,
        item_key: str | None = None,
        quantity: int = 1,
        luck_at: str | None = None,
    ) -> bool:
        now = utc_now()
        self._conn.execute("begin immediate")
        try:
            if self._conn.execute("select 1 from star_payments where charge_id = ?", (charge_id,)).fetchone():
                self._conn.rollback()
                return False
            player = self._conn.execute(
                "select 1 from dig_players where chat_id = ? and user_id = ?",
                (DIG_GLOBAL_CHAT_ID, user_id),
            ).fetchone()
            if player is None:
                self._conn.rollback()
                raise ValueError("Игрок не найден")
            if action == "luck":
                self._conn.execute(
                    "update dig_players set luck = 100, last_luck_at = ?, updated_at = ? where chat_id = ? and user_id = ?",
                    (luck_at or now, now, DIG_GLOBAL_CHAT_ID, user_id),
                )
            elif action == "cooldown":
                self._conn.execute(
                    "update dig_players set last_dig_at = null, updated_at = ? where chat_id = ? and user_id = ?",
                    (now, DIG_GLOBAL_CHAT_ID, user_id),
                )
            elif action == "item" and item_key:
                self._conn.execute(
                    """
                    insert into dig_items(chat_id,user_id,item_key,quantity,updated_at) values(?,?,?,?,?)
                    on conflict(chat_id,user_id,item_key) do update set
                        quantity = quantity + excluded.quantity, updated_at = excluded.updated_at
                    """,
                    (DIG_GLOBAL_CHAT_ID, user_id, item_key, max(1, int(quantity)), now),
                )
            else:
                raise ValueError("Неизвестная покупка шахты")
            self._conn.execute(
                """
                insert into star_payments(user_id,username,full_name,chat_id,amount,currency,charge_id,created_at)
                values(?,?,?,?,?,?,?,?)
                """,
                (user_id, normalize_username(username) if username else None, full_name, chat_id, amount, currency, charge_id, now),
            )
            self._conn.commit()
            return True
        except Exception:
            self._conn.rollback()
            raise

    def has_star_payment_charge(self, charge_id: str) -> bool:
        row = self._conn.execute(
            "select 1 from star_payments where charge_id = ? limit 1",
            (charge_id,),
        ).fetchone()
        return row is not None

    def list_star_payments(self, limit: int = 25) -> list[StarPayment]:
        rows = self._conn.execute(
            """
            select id, user_id, username, full_name, chat_id, amount, currency, charge_id, created_at
            from star_payments
            order by id desc
            limit ?
            """,
            (limit,),
        ).fetchall()
        return [StarPayment(**dict(row)) for row in rows]

    def save_pending_star_message(self, payload: str, user_id: int, chat_id: int, text: str) -> None:
        self._conn.execute(
            """
            insert or replace into pending_star_messages (payload, user_id, chat_id, text, created_at)
            values (?, ?, ?, ?, ?)
            """,
            (payload, user_id, chat_id, text, utc_now()),
        )
        self._conn.commit()

    def get_pending_star_message(self, payload: str) -> PendingStarMessage | None:
        row = self._conn.execute(
            """
            select payload, user_id, chat_id, text, created_at
            from pending_star_messages
            where payload = ?
            """,
            (payload,),
        ).fetchone()
        return PendingStarMessage(**dict(row)) if row else None

    def claim_pending_star_message(self, payload: str) -> PendingStarMessage | None:
        self._conn.execute("begin immediate")
        try:
            row = self._conn.execute(
                "select payload, user_id, chat_id, text, created_at from pending_star_messages where payload = ?",
                (payload,),
            ).fetchone()
            if row is None:
                self._conn.rollback()
                return None
            cur = self._conn.execute("delete from pending_star_messages where payload = ?", (payload,))
            if cur.rowcount != 1:
                self._conn.rollback()
                return None
            self._conn.commit()
            return PendingStarMessage(**dict(row))
        except Exception:
            self._conn.rollback()
            raise

    def delete_pending_star_message(self, payload: str) -> None:
        self._conn.execute("delete from pending_star_messages where payload = ?", (payload,))
        self._conn.commit()

    def save_secret_message_compose(
        self,
        compose_id: str,
        sender_id: int,
        chat_id: int,
        target_id: int,
        target_name: str,
    ) -> None:
        self._conn.execute(
            """
            insert or replace into secret_message_composes
                (compose_id, sender_id, chat_id, target_id, target_name, created_at)
            values (?, ?, ?, ?, ?, ?)
            """,
            (compose_id, sender_id, chat_id, target_id, target_name, utc_now()),
        )
        self._conn.commit()

    def get_secret_message_compose_for_sender(self, sender_id: int) -> SecretMessageCompose | None:
        row = self._conn.execute(
            """
            select compose_id, sender_id, chat_id, target_id, target_name, created_at
            from secret_message_composes
            where sender_id = ?
            order by created_at desc
            limit 1
            """,
            (sender_id,),
        ).fetchone()
        return SecretMessageCompose(**dict(row)) if row else None

    def delete_secret_message_compose(self, compose_id: str) -> None:
        self._conn.execute("delete from secret_message_composes where compose_id = ?", (compose_id,))
        self._conn.commit()

    def save_secret_message(
        self,
        message_id: str,
        chat_id: int,
        sender_id: int,
        sender_username: str | None,
        sender_name: str,
        target_id: int,
        target_name: str,
        text: str,
    ) -> None:
        self._conn.execute(
            """
            insert into secret_messages
                (message_id, chat_id, sender_id, sender_username, sender_name, target_id, target_name, text, created_at, delivered_at)
            values (?, ?, ?, ?, ?, ?, ?, ?, ?, null)
            """,
            (message_id, chat_id, sender_id, sender_username, sender_name, target_id, target_name, text, utc_now()),
        )
        self._conn.commit()

    def get_secret_message(self, message_id: str) -> SecretMessage | None:
        row = self._conn.execute(
            """
            select message_id, chat_id, sender_id, sender_username, sender_name, target_id, target_name, text, created_at, delivered_at
            from secret_messages
            where message_id = ?
            """,
            (message_id,),
        ).fetchone()
        return SecretMessage(**dict(row)) if row else None

    def delete_secret_message(self, message_id: str) -> None:
        self._conn.execute("delete from secret_messages where message_id = ?", (message_id,))
        self._conn.commit()

    def mark_secret_message_delivered(self, message_id: str) -> None:
        self._conn.execute(
            "update secret_messages set delivered_at = coalesce(delivered_at, ?) where message_id = ?",
            (utc_now(), message_id),
        )
        self._conn.commit()

    def create_user_login_request(self, login_id: str, secret_hash: str, expires_at: str) -> None:
        self._conn.execute(
            """
            insert into user_login_requests (login_id, secret_hash, created_at, expires_at)
            values (?, ?, ?, ?)
            """,
            (login_id, secret_hash, utc_now(), expires_at),
        )
        self._conn.commit()

    def get_user_login_request(self, login_id: str) -> UserLoginRequest | None:
        row = self._conn.execute(
            """
            select login_id, secret_hash, user_id, username, full_name, created_at, expires_at, approved_at, consumed_at
            from user_login_requests where login_id = ?
            """,
            (login_id,),
        ).fetchone()
        return UserLoginRequest(**dict(row)) if row else None

    def approve_user_login(self, login_id: str, user_id: int, username: str | None, full_name: str) -> bool:
        cur = self._conn.execute(
            """
            update user_login_requests
            set user_id = ?, username = ?, full_name = ?, approved_at = ?
            where login_id = ? and approved_at is null and consumed_at is null and expires_at > ?
            """,
            (user_id, normalize_username(username) if username else None, full_name, utc_now(), login_id, utc_now()),
        )
        self._conn.commit()
        return cur.rowcount > 0

    def consume_user_login(self, login_id: str) -> bool:
        cur = self._conn.execute(
            "update user_login_requests set consumed_at = ? where login_id = ? and approved_at is not null and consumed_at is null",
            (utc_now(), login_id),
        )
        self._conn.commit()
        return cur.rowcount > 0

    def consume_user_login_and_create_session(
        self,
        login_id: str,
        secret_hash: str,
        token_hash: str,
        user_id: int,
        username: str | None,
        full_name: str,
        expires_at: str,
    ) -> bool:
        now = utc_now()
        self._conn.execute("begin immediate")
        try:
            cur = self._conn.execute(
                """
                update user_login_requests
                set consumed_at = ?
                where login_id = ? and secret_hash = ? and approved_at is not null
                  and consumed_at is null and expires_at > ?
                """,
                (now, login_id, secret_hash, now),
            )
            if cur.rowcount != 1:
                self._conn.rollback()
                return False
            self._conn.execute(
                """
                insert into user_sessions (token_hash, user_id, username, full_name, created_at, expires_at, revoked_at)
                values (?, ?, ?, ?, ?, ?, null)
                """,
                (
                    token_hash,
                    user_id,
                    normalize_username(username) if username else None,
                    full_name,
                    now,
                    expires_at,
                ),
            )
            self._conn.commit()
            return True
        except Exception:
            self._conn.rollback()
            raise

    def create_user_session(
        self,
        token_hash: str,
        user_id: int,
        username: str | None,
        full_name: str,
        expires_at: str,
    ) -> None:
        self._conn.execute(
            """
            insert into user_sessions (token_hash, user_id, username, full_name, created_at, expires_at, revoked_at)
            values (?, ?, ?, ?, ?, ?, null)
            """,
            (token_hash, user_id, normalize_username(username) if username else None, full_name, utc_now(), expires_at),
        )
        self._conn.commit()

    def get_user_session(self, token_hash: str) -> UserSession | None:
        row = self._conn.execute(
            """
            select token_hash, user_id, username, full_name, created_at, expires_at, revoked_at
            from user_sessions where token_hash = ?
            """,
            (token_hash,),
        ).fetchone()
        return UserSession(**dict(row)) if row else None

    def list_user_sessions(self, user_id: int) -> list[UserSession]:
        rows = self._conn.execute(
            """
            select token_hash, user_id, username, full_name, created_at, expires_at, revoked_at
            from user_sessions
            where user_id = ?
            order by created_at desc
            """,
            (user_id,),
        ).fetchall()
        return [UserSession(**dict(row)) for row in rows]

    def revoke_user_session(self, token_hash: str) -> bool:
        cur = self._conn.execute(
            "update user_sessions set revoked_at = ? where token_hash = ? and revoked_at is null",
            (utc_now(), token_hash),
        )
        self._conn.commit()
        return cur.rowcount > 0

    def get_user_subscription(self, user_id: int) -> UserSubscription:
        row = self._conn.execute(
            """
            select user_id, status, expires_at, telegram_payment_charge_id, updated_at
            from user_subscriptions where user_id = ?
            """,
            (user_id,),
        ).fetchone()
        if row:
            return UserSubscription(**dict(row))
        return UserSubscription(user_id=user_id, status="inactive", expires_at=None, telegram_payment_charge_id=None, updated_at=utc_now())

    def set_user_subscription(
        self,
        user_id: int,
        status: str,
        expires_at: str | None,
        charge_id: str | None,
    ) -> None:
        self._conn.execute(
            """
            insert into user_subscriptions (user_id, status, expires_at, telegram_payment_charge_id, updated_at)
            values (?, ?, ?, ?, ?)
            on conflict(user_id) do update set
                status = excluded.status,
                expires_at = excluded.expires_at,
                telegram_payment_charge_id = excluded.telegram_payment_charge_id,
                updated_at = excluded.updated_at
            """,
            (user_id, status, expires_at, charge_id, utc_now()),
        )
        self._conn.commit()

    def add_quote(self, chat_id: int, text: str, author_name: str | None, added_by: int | None) -> None:
        self._conn.execute(
            """
            insert into quotes (chat_id, text, author_name, added_by, created_at)
            values (?, ?, ?, ?, ?)
            """,
            (chat_id, text, author_name, added_by, utc_now()),
        )
        self._conn.commit()

    def random_quote(self, chat_id: int) -> Quote | None:
        row = self._conn.execute(
            """
            select id, chat_id, text, author_name, added_by, created_at
            from quotes
            where chat_id = ?
            order by random()
            limit 1
            """,
            (chat_id,),
        ).fetchone()
        return Quote(**dict(row)) if row else None

    def list_quotes(self, chat_id: int) -> list[Quote]:
        rows = self._conn.execute(
            """
            select id, chat_id, text, author_name, added_by, created_at
            from quotes
            where chat_id = ?
            order by id
            """,
            (chat_id,),
        ).fetchall()
        return [Quote(**dict(row)) for row in rows]

    def delete_quote(self, chat_id: int, quote_id: int) -> bool:
        cur = self._conn.execute(
            "delete from quotes where chat_id = ? and id = ?",
            (chat_id, quote_id),
        )
        self._conn.commit()
        return cur.rowcount > 0

    def add_birthday(self, chat_id: int, day: int, month: int, text: str, added_by: int | None) -> None:
        self._conn.execute(
            """
            insert into birthdays (chat_id, day, month, text, added_by, created_at)
            values (?, ?, ?, ?, ?, ?)
            """,
            (chat_id, day, month, text, added_by, utc_now()),
        )
        self._conn.commit()

    def list_birthdays(self, chat_id: int) -> list[Birthday]:
        rows = self._conn.execute(
            """
            select id, chat_id, day, month, text, added_by, created_at
            from birthdays
            where chat_id = ?
            order by month, day, text collate nocase
            """,
            (chat_id,),
        ).fetchall()
        return [Birthday(**dict(row)) for row in rows]

    def delete_birthday(self, chat_id: int, birthday_id: int) -> bool:
        cur = self._conn.execute(
            "delete from birthdays where chat_id = ? and id = ?",
            (chat_id, birthday_id),
        )
        self._conn.commit()
        return cur.rowcount > 0

    def list_advertisements(self, chat_id: int) -> list[Advertisement]:
        rows = self._conn.execute(
            """
            select id, chat_id, text, enabled, start_time, interval_minutes, duration_type,
                   start_mode, scheduled_at, topic_thread_id, first_sent_at, last_sent_at, created_by, created_at, updated_at
                   , last_error
            from advertisements
            where chat_id = ?
            order by id
            """,
            (chat_id,),
        ).fetchall()
        return [Advertisement(**dict(row)) for row in rows]

    def add_advertisement(
        self,
        chat_id: int,
        text: str,
        enabled: bool,
        start_time: str,
        interval_minutes: int,
        duration_type: str,
        start_mode: str,
        scheduled_at: str,
        topic_thread_id: int | None,
        created_by: int | None,
    ) -> int:
        now = utc_now()
        cur = self._conn.execute(
            """
            insert into advertisements
                (chat_id, text, enabled, start_time, interval_minutes, duration_type, start_mode, scheduled_at,
                 topic_thread_id, created_by, created_at, updated_at)
            values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                chat_id, text.strip(), int(enabled), start_time, max(1, interval_minutes), duration_type,
                start_mode, scheduled_at, topic_thread_id, created_by, now, now,
            ),
        )
        self._conn.commit()
        return int(cur.lastrowid)

    def update_advertisement(
        self,
        chat_id: int,
        ad_id: int,
        text: str,
        enabled: bool,
        start_time: str,
        interval_minutes: int,
        duration_type: str,
        start_mode: str,
        scheduled_at: str,
        topic_thread_id: int | None,
    ) -> bool:
        cur = self._conn.execute(
            """
            update advertisements
            set text = ?, enabled = ?, start_time = ?, interval_minutes = ?, duration_type = ?,
                start_mode = ?, scheduled_at = ?,
                topic_thread_id = ?,
                first_sent_at = null, last_sent_at = null, last_error = null, updated_at = ?
            where chat_id = ? and id = ?
            """,
            (
                text.strip(), int(enabled), start_time, max(1, interval_minutes), duration_type,
                start_mode, scheduled_at, topic_thread_id, utc_now(), chat_id, ad_id,
            ),
        )
        self._conn.commit()
        return cur.rowcount > 0

    def mark_advertisement_sent(self, advertisement_id: int, sent_at: str) -> None:
        self._conn.execute(
            """
            update advertisements
            set first_sent_at = coalesce(first_sent_at, ?), last_sent_at = ?, last_error = null, updated_at = ?
            where id = ?
            """,
            (sent_at, sent_at, utc_now(), advertisement_id),
        )
        self._conn.commit()

    def mark_advertisement_failed(self, advertisement_id: int, error: str) -> None:
        self._conn.execute(
            "update advertisements set last_error = ?, updated_at = ? where id = ?",
            (error[:500], utc_now(), advertisement_id),
        )
        self._conn.commit()

    def list_advertisement_attachments(self, advertisement_id: int) -> list[AdvertisementAttachment]:
        rows = self._conn.execute(
            """
            select id, advertisement_id, media_type, file_id, filename, position
            from advertisement_attachments
            where advertisement_id = ?
            order by position, id
            """,
            (advertisement_id,),
        ).fetchall()
        return [AdvertisementAttachment(**dict(row)) for row in rows]

    def replace_advertisement_attachments(
        self,
        advertisement_id: int,
        attachments: list[tuple[str, str, str]],
    ) -> None:
        self._conn.execute("delete from advertisement_attachments where advertisement_id = ?", (advertisement_id,))
        self._conn.executemany(
            """
            insert into advertisement_attachments (advertisement_id, media_type, file_id, filename, position)
            values (?, ?, ?, ?, ?)
            """,
            [
                (advertisement_id, media_type, file_id, filename, position)
                for position, (media_type, file_id, filename) in enumerate(attachments)
            ],
        )
        self._conn.commit()

    def delete_advertisement(self, chat_id: int, ad_id: int) -> bool:
        self._conn.execute("begin immediate")
        try:
            owned = self._conn.execute(
                "select 1 from advertisements where chat_id = ? and id = ?",
                (chat_id, ad_id),
            ).fetchone()
            if owned is None:
                self._conn.rollback()
                return False
            self._conn.execute("delete from advertisement_attachments where advertisement_id = ?", (ad_id,))
            self._conn.execute("delete from advertisements where chat_id = ? and id = ?", (chat_id, ad_id))
            self._conn.commit()
            return True
        except Exception:
            self._conn.rollback()
            raise

    def get_advertisement_settings(self, chat_id: int) -> AdvertisementSettings:
        row = self._conn.execute(
            """
            select chat_id, enabled, start_time, interval_minutes, next_ad_index, last_sent_at, updated_by, updated_at
            from advertisement_settings
            where chat_id = ?
            """,
            (chat_id,),
        ).fetchone()
        if row:
            return AdvertisementSettings(**dict(row))
        return AdvertisementSettings(chat_id, 0, "09:00", 180, 0, None, None, utc_now())

    def set_advertisement_settings(
        self,
        chat_id: int,
        enabled: bool,
        start_time: str,
        interval_minutes: int,
        updated_by: int | None,
    ) -> None:
        self._conn.execute(
            """
            insert into advertisement_settings
                (chat_id, enabled, start_time, interval_minutes, next_ad_index, last_sent_at, updated_by, updated_at)
            values (?, ?, ?, ?, 0, null, ?, ?)
            on conflict(chat_id) do update set
                enabled = excluded.enabled,
                start_time = excluded.start_time,
                interval_minutes = excluded.interval_minutes,
                next_ad_index = 0,
                last_sent_at = null,
                updated_by = excluded.updated_by,
                updated_at = excluded.updated_at
            """,
            (chat_id, int(enabled), start_time, max(1, interval_minutes), updated_by, utc_now()),
        )
        self._conn.commit()

    def mark_legacy_advertisement_sent(self, chat_id: int, next_ad_index: int, sent_at: str) -> None:
        settings = self.get_advertisement_settings(chat_id)
        self._conn.execute(
            """
            insert into advertisement_settings
                (chat_id, enabled, start_time, interval_minutes, next_ad_index, last_sent_at, updated_by, updated_at)
            values (?, ?, ?, ?, ?, ?, ?, ?)
            on conflict(chat_id) do update set
                next_ad_index = excluded.next_ad_index,
                last_sent_at = excluded.last_sent_at,
                updated_at = excluded.updated_at
            """,
            (
                chat_id,
                settings.enabled,
                settings.start_time,
                settings.interval_minutes,
                next_ad_index,
                sent_at,
                settings.updated_by,
                utc_now(),
            ),
        )
        self._conn.commit()

    def birthdays_for_date(self, chat_id: int, day: int, month: int, sent_date: str) -> list[Birthday]:
        rows = self._conn.execute(
            """
            select b.id, b.chat_id, b.day, b.month, b.text, b.added_by, b.created_at
            from birthdays b
            left join birthday_sent s
                on s.chat_id = b.chat_id and s.birthday_id = b.id and s.sent_date = ?
            where b.chat_id = ? and b.day = ? and b.month = ? and s.birthday_id is null
            order by b.text collate nocase
            """,
            (sent_date, chat_id, day, month),
        ).fetchall()
        return [Birthday(**dict(row)) for row in rows]

    def mark_birthday_sent(self, chat_id: int, birthday_id: int, sent_date: str) -> None:
        self._conn.execute(
            "insert or ignore into birthday_sent (chat_id, birthday_id, sent_date) values (?, ?, ?)",
            (chat_id, birthday_id, sent_date),
        )
        self._conn.commit()

    def add_blacklist_word(self, chat_id: int, word: str, added_by: int | None) -> None:
        self._conn.execute(
            """
            insert into blacklist_words (chat_id, word, added_by, created_at)
            values (?, ?, ?, ?)
            on conflict(chat_id, word) do update set
                added_by = excluded.added_by,
                created_at = excluded.created_at
            """,
            (chat_id, normalize_trigger(word), added_by, utc_now()),
        )
        self._conn.commit()

    def delete_blacklist_word(self, chat_id: int, word: str) -> bool:
        cur = self._conn.execute(
            "delete from blacklist_words where chat_id = ? and word = ?",
            (chat_id, normalize_trigger(word)),
        )
        self._conn.commit()
        return cur.rowcount > 0

    def list_blacklist_words(self, chat_id: int) -> list[BlacklistWord]:
        rows = self._conn.execute(
            """
            select chat_id, word, added_by, created_at
            from blacklist_words
            where chat_id = ?
            order by word collate nocase
            """,
            (chat_id,),
        ).fetchall()
        return [BlacklistWord(**dict(row)) for row in rows]

    def get_roll_mute_settings(self, chat_id: int) -> RollMuteSettings:
        row = self._conn.execute(
            """
            select chat_id, mute_minutes, cooldown_minutes, updated_by, updated_at, last_used_at
            from roll_mute_settings
            where chat_id = ?
            """,
            (chat_id,),
        ).fetchone()
        if row:
            return RollMuteSettings(**dict(row))
        return RollMuteSettings(
            chat_id=chat_id,
            mute_minutes=60,
            cooldown_minutes=30,
            updated_by=None,
            updated_at=utc_now(),
            last_used_at=None,
        )

    def set_roll_mute_settings(
        self,
        chat_id: int,
        mute_minutes: int,
        cooldown_minutes: int,
        updated_by: int | None,
    ) -> None:
        current = self.get_roll_mute_settings(chat_id)
        self._conn.execute(
            """
            insert into roll_mute_settings (chat_id, mute_minutes, cooldown_minutes, updated_by, updated_at, last_used_at)
            values (?, ?, ?, ?, ?, ?)
            on conflict(chat_id) do update set
                mute_minutes = excluded.mute_minutes,
                cooldown_minutes = excluded.cooldown_minutes,
                updated_by = excluded.updated_by,
                updated_at = excluded.updated_at
            """,
            (
                chat_id,
                max(1, min(10080, int(mute_minutes))),
                max(0, min(10080, int(cooldown_minutes))),
                updated_by,
                utc_now(),
                current.last_used_at,
            ),
        )
        self._conn.commit()

    def set_roll_mute_last_used(self, chat_id: int, used_at: str) -> None:
        current = self.get_roll_mute_settings(chat_id)
        self._conn.execute(
            """
            insert into roll_mute_settings (chat_id, mute_minutes, cooldown_minutes, updated_by, updated_at, last_used_at)
            values (?, ?, ?, ?, ?, ?)
            on conflict(chat_id) do update set
                last_used_at = excluded.last_used_at
            """,
            (chat_id, current.mute_minutes, current.cooldown_minutes, current.updated_by, current.updated_at, used_at),
        )
        self._conn.commit()

    def claim_roll_mute(self, chat_id: int, used_at: str, cutoff_at: str) -> bool:
        self._conn.execute("begin immediate")
        try:
            current = self._conn.execute(
                """
                select mute_minutes, cooldown_minutes, updated_by, updated_at, last_used_at
                from roll_mute_settings where chat_id = ?
                """,
                (chat_id,),
            ).fetchone()
            if current and current["last_used_at"] and current["last_used_at"] > cutoff_at:
                self._conn.rollback()
                return False
            mute_minutes = int(current["mute_minutes"]) if current else 60
            cooldown_minutes = int(current["cooldown_minutes"]) if current else 30
            updated_by = current["updated_by"] if current else None
            updated_at = current["updated_at"] if current else used_at
            self._conn.execute(
                """
                insert into roll_mute_settings
                    (chat_id, mute_minutes, cooldown_minutes, updated_by, updated_at, last_used_at)
                values (?, ?, ?, ?, ?, ?)
                on conflict(chat_id) do update set last_used_at = excluded.last_used_at
                """,
                (chat_id, mute_minutes, cooldown_minutes, updated_by, updated_at, used_at),
            )
            self._conn.commit()
            return True
        except Exception:
            self._conn.rollback()
            raise

    def increment_roll_mute_stat(self, chat_id: int, user_id: int) -> None:
        self._conn.execute(
            """
            insert into roll_mute_stats (chat_id, user_id, unlucky_count, updated_at)
            values (?, ?, 1, ?)
            on conflict(chat_id, user_id) do update set
                unlucky_count = unlucky_count + 1,
                updated_at = excluded.updated_at
            """,
            (chat_id, user_id, utc_now()),
        )
        self._conn.commit()

    def top_roll_mute_stats(self, chat_id: int, limit: int | None = 10) -> list[RollMuteStat]:
        query = """
            select
                s.chat_id,
                s.user_id,
                u.username,
                coalesce(u.full_name, 'user ' || s.user_id) as full_name,
                s.unlucky_count
            from roll_mute_stats s
            left join seen_users u on u.chat_id = s.chat_id and u.user_id = s.user_id
            where s.chat_id = ?
            order by s.unlucky_count desc, u.username collate nocase
        """
        params: tuple = (chat_id,)
        if limit is not None:
            query += " limit ?"
            params = (chat_id, limit)
        rows = self._conn.execute(query, params).fetchall()
        return [RollMuteStat(**dict(row)) for row in rows]

    def roll_mute_count_for_user(self, chat_id: int, user_id: int) -> int:
        row = self._conn.execute(
            "select unlucky_count from roll_mute_stats where chat_id = ? and user_id = ?",
            (chat_id, user_id),
        ).fetchone()
        return int(row["unlucky_count"]) if row else 0

    def giveaway_wins_for_user(self, chat_id: int, user_id: int) -> int:
        row = self._conn.execute(
            "select wins_count from giveaway_stats where chat_id = ? and user_id = ?",
            (chat_id, user_id),
        ).fetchone()
        return int(row["wins_count"]) if row else 0

    def message_count_for_user(self, chat_id: int, user_id: int) -> int:
        row = self._conn.execute(
            """
            select coalesce(sum(messages_count), 0) as total
            from participant_activity_daily
            where chat_id = ? and user_id = ?
            """,
            (chat_id, user_id),
        ).fetchone()
        return int(row["total"]) if row else 0

    def get_quiet_settings(self, chat_id: int) -> QuietSettings:
        row = self._conn.execute(
            """
            select chat_id, reply_text, media_type, media_file_id, updated_by, updated_at
            from quiet_settings
            where chat_id = ?
            """,
            (chat_id,),
        ).fetchone()
        if row:
            return QuietSettings(**dict(row))
        return QuietSettings(
            chat_id=chat_id,
            reply_text=None,
            media_type=None,
            media_file_id=None,
            updated_by=None,
            updated_at=utc_now(),
        )

    def set_quiet_text(self, chat_id: int, reply_text: str, updated_by: int | None) -> None:
        current = self.get_quiet_settings(chat_id)
        self._conn.execute(
            """
            insert into quiet_settings (chat_id, reply_text, media_type, media_file_id, updated_by, updated_at)
            values (?, ?, ?, ?, ?, ?)
            on conflict(chat_id) do update set
                reply_text = excluded.reply_text,
                updated_by = excluded.updated_by,
                updated_at = excluded.updated_at
            """,
            (chat_id, reply_text.strip(), current.media_type, current.media_file_id, updated_by, utc_now()),
        )
        self._conn.commit()

    def set_quiet_media(self, chat_id: int, media_type: str, media_file_id: str, updated_by: int | None) -> None:
        current = self.get_quiet_settings(chat_id)
        self._conn.execute(
            """
            insert into quiet_settings (chat_id, reply_text, media_type, media_file_id, updated_by, updated_at)
            values (?, ?, ?, ?, ?, ?)
            on conflict(chat_id) do update set
                media_type = excluded.media_type,
                media_file_id = excluded.media_file_id,
                updated_by = excluded.updated_by,
                updated_at = excluded.updated_at
            """,
            (chat_id, current.reply_text, media_type, media_file_id, updated_by, utc_now()),
        )
        self._conn.commit()

    def clear_quiet_media(self, chat_id: int, updated_by: int | None) -> None:
        current = self.get_quiet_settings(chat_id)
        self._conn.execute(
            """
            insert into quiet_settings (chat_id, reply_text, media_type, media_file_id, updated_by, updated_at)
            values (?, ?, null, null, ?, ?)
            on conflict(chat_id) do update set
                media_type = null,
                media_file_id = null,
                updated_by = excluded.updated_by,
                updated_at = excluded.updated_at
            """,
            (chat_id, current.reply_text, updated_by, utc_now()),
        )
        self._conn.commit()

    def set_quiet_admin(
        self,
        chat_id: int,
        user_id: int,
        username: str | None,
        full_name: str,
        reason: str,
        until_at: str,
        created_by: int | None,
    ) -> None:
        self._conn.execute(
            """
            insert into quiet_admins (chat_id, user_id, username, full_name, reason, until_at, created_by, created_at)
            values (?, ?, ?, ?, ?, ?, ?, ?)
            on conflict(chat_id, user_id) do update set
                username = excluded.username,
                full_name = excluded.full_name,
                reason = excluded.reason,
                until_at = excluded.until_at,
                created_by = excluded.created_by,
                created_at = excluded.created_at
            """,
            (
                chat_id,
                user_id,
                normalize_username(username) if username else None,
                full_name,
                reason.strip(),
                until_at,
                created_by,
                utc_now(),
            ),
        )
        self._conn.commit()

    def get_active_quiet_admin(self, chat_id: int, user_id: int, now: str | None = None) -> QuietAdmin | None:
        now = now or utc_now()
        row = self._conn.execute(
            """
            select chat_id, user_id, username, full_name, reason, until_at, created_by, created_at
            from quiet_admins
            where chat_id = ? and user_id = ?
            """,
            (chat_id, user_id),
        ).fetchone()
        if not row:
            return None
        if str(row["until_at"]) <= now:
            self._conn.execute("delete from quiet_admins where chat_id = ? and user_id = ?", (chat_id, user_id))
            self._conn.commit()
            return None
        return QuietAdmin(**dict(row))

    def clear_quiet_admin(self, chat_id: int, user_id: int) -> bool:
        cur = self._conn.execute(
            "delete from quiet_admins where chat_id = ? and user_id = ?",
            (chat_id, user_id),
        )
        self._conn.commit()
        return cur.rowcount > 0

    def get_dig_player(self, chat_id: int, user_id: int) -> DigPlayer | None:
        chat_id = DIG_GLOBAL_CHAT_ID
        row = self._conn.execute(
            """
            select chat_id, user_id, username, full_name, coins, total_depth, best_session_depth,
                   luck, last_luck_at, last_dig_at, created_at, updated_at
            from dig_players
            where chat_id = ? and user_id = ?
            """,
            (chat_id, user_id),
        ).fetchone()
        return DigPlayer(**dict(row)) if row else None

    def register_dig_player(self, chat_id: int, user_id: int, username: str | None, full_name: str) -> bool:
        chat_id = DIG_GLOBAL_CHAT_ID
        now = utc_now()
        cur = self._conn.execute(
            """
            insert or ignore into dig_players (
                chat_id, user_id, username, full_name, coins, total_depth, best_session_depth,
                luck, last_luck_at, last_dig_at, created_at, updated_at
            )
            values (?, ?, ?, ?, 0, 0, 0, 100, ?, null, ?, ?)
            """,
            (chat_id, user_id, normalize_username(username) if username else None, full_name, now, now, now),
        )
        if cur.rowcount == 0:
            self._conn.execute(
                """
                update dig_players
                set username = ?, full_name = ?, updated_at = ?
                where chat_id = ? and user_id = ?
                """,
                (normalize_username(username) if username else None, full_name, now, chat_id, user_id),
            )
        self._conn.commit()
        return cur.rowcount > 0

    def update_dig_player_after_dig(
        self,
        chat_id: int,
        user_id: int,
        username: str | None,
        full_name: str,
        coins_delta: int,
        depth_delta: int,
        best_session_depth: int,
        luck: int,
        last_luck_at: str,
        last_dig_at: str,
    ) -> None:
        chat_id = DIG_GLOBAL_CHAT_ID
        self._conn.execute(
            """
            update dig_players
            set username = ?,
                full_name = ?,
                coins = coins + ?,
                total_depth = total_depth + ?,
                best_session_depth = max(best_session_depth, ?),
                luck = ?,
                last_luck_at = ?,
                last_dig_at = ?,
                updated_at = ?
            where chat_id = ? and user_id = ?
            """,
            (
                normalize_username(username) if username else None,
                full_name,
                max(0, int(coins_delta)),
                max(0, int(depth_delta)),
                max(0, int(best_session_depth)),
                max(0, min(100, int(luck))),
                last_luck_at,
                last_dig_at,
                utc_now(),
                chat_id,
                user_id,
            ),
        )
        self._conn.commit()

    def top_dig_depth(self, chat_id: int, limit: int | None = 10) -> list[DigPlayer]:
        chat_id = DIG_GLOBAL_CHAT_ID
        query = """
            select chat_id, user_id, username, full_name, coins, total_depth, best_session_depth,
                   luck, last_luck_at, last_dig_at, created_at, updated_at
            from dig_players
            where chat_id = ?
            order by total_depth desc, best_session_depth desc, coins desc
        """
        params: tuple = (chat_id,)
        if limit is not None:
            query += " limit ?"
            params = (chat_id, limit)
        rows = self._conn.execute(query, params).fetchall()
        return [DigPlayer(**dict(row)) for row in rows]

    def top_dig_coins(self, chat_id: int, limit: int | None = 10) -> list[DigPlayer]:
        chat_id = DIG_GLOBAL_CHAT_ID
        query = """
            select chat_id, user_id, username, full_name, coins, total_depth, best_session_depth,
                   luck, last_luck_at, last_dig_at, created_at, updated_at
            from dig_players
            where chat_id = ?
            order by coins desc, total_depth desc
        """
        params: tuple = (chat_id,)
        if limit is not None:
            query += " limit ?"
            params = (chat_id, limit)
        rows = self._conn.execute(query, params).fetchall()
        return [DigPlayer(**dict(row)) for row in rows]

    def list_all_dig_players(self) -> list[DigPlayer]:
        rows = self._conn.execute(
            """
            select chat_id, user_id, username, full_name, coins, total_depth, best_session_depth,
                   luck, last_luck_at, last_dig_at, created_at, updated_at
            from dig_players
            order by chat_id, user_id
            """
        ).fetchall()
        return [DigPlayer(**dict(row)) for row in rows]

    def count_dig_players(self) -> int:
        row = self._conn.execute("select count(*) as total from dig_players").fetchone()
        return int(row["total"]) if row else 0

    def list_dig_players_page(self, limit: int = 20, offset: int = 0) -> list[DigPlayer]:
        rows = self._conn.execute(
            """
            select chat_id, user_id, username, full_name, coins, total_depth, best_session_depth,
                   luck, last_luck_at, last_dig_at, created_at, updated_at
            from dig_players
            order by total_depth desc, best_session_depth desc, coins desc, full_name collate nocase
            limit ? offset ?
            """,
            (max(1, int(limit)), max(0, int(offset))),
        ).fetchall()
        return [DigPlayer(**dict(row)) for row in rows]

    def list_dig_items(self, chat_id: int, user_id: int) -> list[DigItem]:
        chat_id = DIG_GLOBAL_CHAT_ID
        rows = self._conn.execute(
            """
            select chat_id, user_id, item_key, quantity, updated_at
            from dig_items
            where chat_id = ? and user_id = ? and quantity > 0
            order by item_key collate nocase
            """,
            (chat_id, user_id),
        ).fetchall()
        return [DigItem(**dict(row)) for row in rows]

    def get_dig_player_tag(self, user_id: int) -> str | None:
        row = self._conn.execute(
            "select tag from dig_player_tags where user_id = ?",
            (int(user_id),),
        ).fetchone()
        return str(row["tag"]) if row else None

    def set_dig_player_tag(self, user_id: int, tag: str) -> None:
        self._conn.execute(
            """
            insert into dig_player_tags (user_id, tag, updated_at)
            values (?, ?, ?)
            on conflict(user_id) do update set
                tag = excluded.tag,
                updated_at = excluded.updated_at
            """,
            (int(user_id), tag, utc_now()),
        )
        self._conn.commit()

    def get_miniapp_profile_role(self, user_id: int) -> MiniAppProfileRole | None:
        row = self._conn.execute(
            """
            select user_id, label, emoji, color, granted_by, updated_at
            from miniapp_profile_roles
            where user_id = ?
            """,
            (int(user_id),),
        ).fetchone()
        return MiniAppProfileRole(**dict(row)) if row else None

    def set_miniapp_profile_role(
        self,
        user_id: int,
        label: str,
        granted_by: int | None,
        emoji: str | None = None,
        color: str | None = None,
    ) -> None:
        self._conn.execute(
            """
            insert into miniapp_profile_roles (user_id, label, emoji, color, granted_by, updated_at)
            values (?, ?, ?, ?, ?, ?)
            on conflict(user_id) do update set
                label = excluded.label,
                emoji = excluded.emoji,
                color = excluded.color,
                granted_by = excluded.granted_by,
                updated_at = excluded.updated_at
            """,
            (int(user_id), label.strip()[:16], emoji, color, granted_by, utc_now()),
        )
        self._conn.commit()

    def clear_miniapp_profile_role(self, user_id: int) -> bool:
        cur = self._conn.execute(
            "delete from miniapp_profile_roles where user_id = ?",
            (int(user_id),),
        )
        self._conn.commit()
        return cur.rowcount > 0

    def list_miniapp_profile_roles(self) -> list[dict]:
        rows = self._conn.execute(
            """
            select
                r.user_id,
                r.label,
                r.emoji,
                r.color,
                r.granted_by,
                r.updated_at,
                coalesce(u.username, '') as username,
                coalesce(u.full_name, cast(r.user_id as text)) as full_name
            from miniapp_profile_roles r
            left join (
                select user_id, max(nullif(username, '')) as username, max(nullif(full_name, '')) as full_name
                from seen_users
                where coalesce(is_bot, 0) = 0
                group by user_id
            ) u on u.user_id = r.user_id
            order by r.updated_at desc
            """
        ).fetchall()
        return [dict(row) for row in rows]

    def list_miniapp_profile_roles_by_label(self, labels: list[str]) -> list[dict]:
        if not labels:
            return []
        placeholders = ",".join("?" for _ in labels)
        rows = self._conn.execute(
            f"""
            select
                r.user_id,
                r.label,
                r.emoji,
                r.color,
                r.granted_by,
                r.updated_at,
                coalesce(u.username, '') as username,
                coalesce(u.full_name, cast(r.user_id as text)) as full_name
            from miniapp_profile_roles r
            left join (
                select user_id, max(nullif(username, '')) as username, max(nullif(full_name, '')) as full_name
                from seen_users
                where coalesce(is_bot, 0) = 0
                group by user_id
            ) u on u.user_id = r.user_id
            where r.label in ({placeholders})
            order by r.label, lower(coalesce(u.full_name, cast(r.user_id as text)))
            """,
            tuple(labels),
        ).fetchall()
        return [dict(row) for row in rows]

    def list_miniapp_chat_admins(self) -> list[dict]:
        rows = self._conn.execute(
            """
            with admins as (
                select chat_id, user_id
                from chat_admin_feature_permissions
                where allowed = 1
                union
                select chat_id, user_id
                from chat_telegram_admins
                where is_bot = 0
            )
            select
                a.user_id,
                count(distinct a.chat_id) as chat_count,
                coalesce(u.username, '') as username,
                coalesce(u.full_name, cast(a.user_id as text)) as full_name
            from admins a
            left join (
                select user_id, max(nullif(username, '')) as username, max(nullif(full_name, '')) as full_name
                from seen_users
                where coalesce(is_bot, 0) = 0
                group by user_id
            ) u on u.user_id = a.user_id
            group by a.user_id
            order by lower(coalesce(u.full_name, cast(a.user_id as text)))
            """
        ).fetchall()
        return [dict(row) for row in rows]

    def get_known_user_by_username(self, username: str) -> SeenUser | None:
        normalized = normalize_username(username)
        row = self._conn.execute(
            """
            select
                u.chat_id,
                u.user_id,
                u.username,
                coalesce(nullif(u.full_name, ''), 'Игрок') as full_name,
                u.is_bot,
                u.updated_at
            from seen_users u
            where u.username = ? and coalesce(u.is_bot, 0) = 0
            order by u.updated_at desc
            limit 1
            """,
            (normalized,),
        ).fetchone()
        return SeenUser(**dict(row)) if row else None

    def list_user_moderator_roles(self, user_id: int, now: str | None = None) -> list[dict]:
        check_at = now or utc_now()
        rows = self._conn.execute(
            """
            select r.chat_id, r.user_id, r.role, r.granted_at, r.expires_at, coalesce(c.title, cast(r.chat_id as text)) as chat_title
            from chat_moderator_roles r
            left join chats c on c.chat_id = r.chat_id
            where r.user_id = ? and r.active = 1
              and (r.expires_at is null or r.expires_at > ?)
            order by r.granted_at desc
            """,
            (int(user_id), check_at),
        ).fetchall()
        return [dict(row) for row in rows]

    def get_dig_item_quantity(self, chat_id: int, user_id: int, item_key: str) -> int:
        chat_id = DIG_GLOBAL_CHAT_ID
        row = self._conn.execute(
            """
            select quantity from dig_items
            where chat_id = ? and user_id = ? and item_key = ?
            """,
            (chat_id, user_id, item_key),
        ).fetchone()
        return int(row["quantity"]) if row else 0

    def add_dig_item(self, chat_id: int, user_id: int, item_key: str, quantity: int = 1) -> None:
        chat_id = DIG_GLOBAL_CHAT_ID
        self._conn.execute(
            """
            insert into dig_items (chat_id, user_id, item_key, quantity, updated_at)
            values (?, ?, ?, ?, ?)
            on conflict(chat_id, user_id, item_key) do update set
                quantity = quantity + excluded.quantity,
                updated_at = excluded.updated_at
            """,
            (chat_id, user_id, item_key, max(1, int(quantity)), utc_now()),
        )
        self._conn.commit()

    def consume_dig_item(self, chat_id: int, user_id: int, item_key: str) -> bool:
        chat_id = DIG_GLOBAL_CHAT_ID
        cur = self._conn.execute(
            """
            update dig_items
            set quantity = quantity - 1, updated_at = ?
            where chat_id = ? and user_id = ? and item_key = ? and quantity > 0
            """,
            (utc_now(), chat_id, user_id, item_key),
        )
        self._conn.commit()
        return cur.rowcount > 0

    def consume_dig_items(self, chat_id: int, user_id: int, item_key: str, quantity: int) -> bool:
        chat_id = DIG_GLOBAL_CHAT_ID
        quantity = max(1, int(quantity))
        cur = self._conn.execute(
            """
            update dig_items
            set quantity = quantity - ?, updated_at = ?
            where chat_id = ? and user_id = ? and item_key = ? and quantity >= ?
            """,
            (quantity, utc_now(), chat_id, user_id, item_key, quantity),
        )
        self._conn.commit()
        return cur.rowcount > 0

    def spend_dig_coins(self, chat_id: int, user_id: int, amount: int) -> bool:
        chat_id = DIG_GLOBAL_CHAT_ID
        cur = self._conn.execute(
            """
            update dig_players
            set coins = coins - ?, updated_at = ?
            where chat_id = ? and user_id = ? and coins >= ?
            """,
            (max(0, int(amount)), utc_now(), chat_id, user_id, max(0, int(amount))),
        )
        self._conn.commit()
        return cur.rowcount > 0

    def add_dig_coins(self, chat_id: int, user_id: int, amount: int) -> None:
        chat_id = DIG_GLOBAL_CHAT_ID
        self._conn.execute(
            """
            update dig_players
            set coins = max(0, coins + ?), updated_at = ?
            where chat_id = ? and user_id = ?
            """,
            (int(amount), utc_now(), chat_id, user_id),
        )
        self._conn.commit()

    def adjust_dig_item(self, chat_id: int, user_id: int, item_key: str, quantity_delta: int) -> None:
        chat_id = DIG_GLOBAL_CHAT_ID
        current = self.get_dig_item_quantity(chat_id, user_id, item_key)
        next_quantity = max(0, current + int(quantity_delta))
        self._conn.execute(
            """
            insert into dig_items (chat_id, user_id, item_key, quantity, updated_at)
            values (?, ?, ?, ?, ?)
            on conflict(chat_id, user_id, item_key) do update set
                quantity = excluded.quantity,
                updated_at = excluded.updated_at
            """,
            (chat_id, user_id, item_key, next_quantity, utc_now()),
        )
        self._conn.commit()

    def purchase_dig_item(
        self,
        chat_id: int,
        user_id: int,
        item_key: str,
        price: int,
        quantity: int = 1,
        unique: bool = False,
    ) -> str:
        chat_id = DIG_GLOBAL_CHAT_ID
        now = utc_now()
        try:
            self._conn.execute("begin immediate")
            if unique:
                row = self._conn.execute(
                    """
                    select quantity from dig_items
                    where chat_id = ? and user_id = ? and item_key = ?
                    """,
                    (chat_id, user_id, item_key),
                ).fetchone()
                if row and int(row["quantity"]) > 0:
                    self._conn.rollback()
                    return "owned"

            cur = self._conn.execute(
                """
                update dig_players
                set coins = coins - ?, updated_at = ?
                where chat_id = ? and user_id = ? and coins >= ?
                """,
                (max(0, int(price)), now, chat_id, user_id, max(0, int(price))),
            )
            if cur.rowcount == 0:
                self._conn.rollback()
                return "no_coins"

            self._conn.execute(
                """
                insert into dig_items (chat_id, user_id, item_key, quantity, updated_at)
                values (?, ?, ?, ?, ?)
                on conflict(chat_id, user_id, item_key) do update set
                    quantity = quantity + excluded.quantity,
                    updated_at = excluded.updated_at
                """,
                (chat_id, user_id, item_key, max(1, int(quantity)), now),
            )
            self._conn.commit()
            return "ok"
        except Exception:
            self._conn.rollback()
            raise

    def set_dig_luck(self, chat_id: int, user_id: int, luck: int, last_luck_at: str) -> None:
        chat_id = DIG_GLOBAL_CHAT_ID
        self._conn.execute(
            """
            update dig_players
            set luck = ?, last_luck_at = ?, updated_at = ?
            where chat_id = ? and user_id = ?
            """,
            (max(0, min(100, int(luck))), last_luck_at, utc_now(), chat_id, user_id),
        )
        self._conn.commit()

    def clear_dig_cooldown(self, chat_id: int, user_id: int) -> None:
        chat_id = DIG_GLOBAL_CHAT_ID
        self._conn.execute(
            """
            update dig_players
            set last_dig_at = null, updated_at = ?
            where chat_id = ? and user_id = ?
            """,
            (utc_now(), chat_id, user_id),
        )
        self._conn.commit()

    def delete_dig_player(self, user_id: int) -> bool:
        chat_id = DIG_GLOBAL_CHAT_ID
        uid = int(user_id)
        try:
            self._conn.execute("begin immediate")
            existed = self._conn.execute(
                "select 1 from dig_players where chat_id = ? and user_id = ?",
                (chat_id, uid),
            ).fetchone()
            for table in (
                "dig_items",
                "dig_achievements",
                "dig_players",
            ):
                self._conn.execute(
                    f"delete from {table} where chat_id = ? and user_id = ?",
                    (chat_id, uid),
                )
            for table in (
                "dig_progress",
                "dig_sessions",
                "interactive_dig_sessions",
                "dig_weekly_depth",
                "gold_ticket_games",
                "super_ticket_games",
                "dig_contracts",
            ):
                self._conn.execute(f"delete from {table} where user_id = ?", (uid,))
            self._conn.execute("delete from dig_expedition_contributors where user_id = ?", (uid,))
            self._conn.execute("delete from dig_player_tags where user_id = ?", (uid,))
            self._conn.commit()
            return existed is not None
        except Exception:
            self._conn.rollback()
            raise

    def block_dig_user(self, user_id: int, blocked_by: int | None, reason: str = "") -> None:
        self._conn.execute(
            """
            insert into dig_blocked_users (user_id, reason, blocked_by, created_at)
            values (?, ?, ?, ?)
            on conflict(user_id) do update set
                reason = excluded.reason,
                blocked_by = excluded.blocked_by,
                created_at = excluded.created_at
            """,
            (int(user_id), reason.strip()[:500], blocked_by, utc_now()),
        )
        self._conn.commit()

    def unblock_dig_user(self, user_id: int) -> bool:
        cur = self._conn.execute("delete from dig_blocked_users where user_id = ?", (int(user_id),))
        self._conn.commit()
        return cur.rowcount > 0

    def get_dig_block(self, user_id: int) -> dict | None:
        row = self._conn.execute(
            """
            select user_id, reason, blocked_by, created_at
            from dig_blocked_users
            where user_id = ?
            """,
            (int(user_id),),
        ).fetchone()
        return dict(row) if row else None

    def list_dig_blocks(self) -> list[dict]:
        rows = self._conn.execute(
            """
            select
                b.user_id,
                b.reason,
                b.blocked_by,
                b.created_at,
                coalesce(u.username, '') as username,
                coalesce(u.full_name, cast(b.user_id as text)) as full_name
            from dig_blocked_users b
            left join (
                select user_id, max(nullif(username, '')) as username, max(nullif(full_name, '')) as full_name
                from seen_users
                where coalesce(is_bot, 0) = 0
                group by user_id
            ) u on u.user_id = b.user_id
            order by b.created_at desc
            """
        ).fetchall()
        return [dict(row) for row in rows]

    def add_dig_achievement(self, chat_id: int, user_id: int, achievement_key: str) -> bool:
        chat_id = DIG_GLOBAL_CHAT_ID
        cur = self._conn.execute(
            """
            insert or ignore into dig_achievements (chat_id, user_id, achievement_key, created_at)
            values (?, ?, ?, ?)
            """,
            (chat_id, user_id, achievement_key, utc_now()),
        )
        self._conn.commit()
        return cur.rowcount > 0

    def list_dig_achievements(self, chat_id: int, user_id: int) -> list[DigAchievement]:
        chat_id = DIG_GLOBAL_CHAT_ID
        rows = self._conn.execute(
            """
            select chat_id, user_id, achievement_key, created_at
            from dig_achievements
            where chat_id = ? and user_id = ?
            order by created_at
            """,
            (chat_id, user_id),
        ).fetchall()
        return [DigAchievement(**dict(row)) for row in rows]

    def get_dig_progress(self, user_id: int) -> dict:
        row = self._conn.execute(
            "select xp, level, streak, selected_route, last_dig_date, updated_at from dig_progress where user_id = ?",
            (user_id,),
        ).fetchone()
        if row is None:
            player = self.get_dig_player(DIG_GLOBAL_CHAT_ID, user_id)
            xp = max(0, (player.total_depth if player else 0) * 10)
            level = min(50, 1 + xp // 250)
            now = utc_now()
            self._conn.execute(
                "insert into dig_progress(user_id, xp, level, streak, selected_route, updated_at) values (?, ?, ?, 0, 'old_mine', ?)",
                (user_id, xp, level, now),
            )
            self._conn.commit()
            row = self._conn.execute(
                "select xp, level, streak, selected_route, last_dig_date, updated_at from dig_progress where user_id = ?",
                (user_id,),
            ).fetchone()
        return dict(row)

    def update_dig_progress(self, user_id: int, xp_delta: int, success: bool, route: str | None = None) -> dict:
        current = self.get_dig_progress(user_id)
        xp = max(0, int(current["xp"]) + max(0, int(xp_delta)))
        level = min(50, 1 + xp // 250)
        streak = int(current["streak"]) + 1 if success else 0
        selected_route = route or str(current["selected_route"])
        today = datetime.now(timezone.utc).date().isoformat()
        self._conn.execute(
            """
            update dig_progress
            set xp = ?, level = ?, streak = ?, selected_route = ?, last_dig_date = ?, updated_at = ?
            where user_id = ?
            """,
            (xp, level, streak, selected_route, today, utc_now(), user_id),
        )
        self._conn.commit()
        return self.get_dig_progress(user_id)

    def set_dig_route(self, user_id: int, route: str) -> None:
        self.get_dig_progress(user_id)
        self._conn.execute(
            "update dig_progress set selected_route = ?, updated_at = ? where user_id = ?",
            (route, utc_now(), user_id),
        )
        self._conn.commit()

    def ensure_dig_contracts(self, user_id: int, contract_date: str, contracts: list[tuple[str, int]]) -> None:
        self._conn.executemany(
            """
            insert or ignore into dig_contracts(user_id, contract_date, contract_key, target, progress, claimed)
            values (?, ?, ?, ?, 0, 0)
            """,
            [(user_id, contract_date, key, target) for key, target in contracts],
        )
        self._conn.commit()

    def list_dig_contracts(self, user_id: int, contract_date: str) -> list[dict]:
        return [
            dict(row)
            for row in self._conn.execute(
                """
                select contract_key, target, progress, claimed
                from dig_contracts where user_id = ? and contract_date = ? order by contract_key
                """,
                (user_id, contract_date),
            ).fetchall()
        ]

    def add_dig_contract_progress(self, user_id: int, contract_date: str, values: dict[str, int]) -> None:
        for key, amount in values.items():
            if amount <= 0:
                continue
            self._conn.execute(
                """
                update dig_contracts set progress = min(target, progress + ?)
                where user_id = ? and contract_date = ? and contract_key = ? and claimed = 0
                """,
                (int(amount), user_id, contract_date, key),
            )
        self._conn.commit()

    def claim_ready_dig_contracts(self, user_id: int, contract_date: str) -> list[str]:
        rows = self._conn.execute(
            """
            select contract_key from dig_contracts
            where user_id = ? and contract_date = ? and claimed = 0 and progress >= target
            """,
            (user_id, contract_date),
        ).fetchall()
        keys = [str(row["contract_key"]) for row in rows]
        if keys:
            self._conn.executemany(
                "update dig_contracts set claimed = 1 where user_id = ? and contract_date = ? and contract_key = ?",
                [(user_id, contract_date, key) for key in keys],
            )
            self._conn.commit()
        return keys

    def add_dig_weekly_depth(self, user_id: int, week_start: str, depth: int) -> None:
        if depth <= 0:
            return
        self._conn.execute(
            """
            insert into dig_weekly_depth(week_start, user_id, depth) values (?, ?, ?)
            on conflict(week_start, user_id) do update set depth = depth + excluded.depth
            """,
            (week_start, int(user_id), int(depth)),
        )
        self._conn.commit()

    def list_dig_weekly_rankings(self, week_start: str, limit: int = 100) -> list[dict]:
        rows = self._conn.execute(
            """
            select w.user_id, w.depth, p.username, p.full_name,
                   max(case when i.item_key = 'rank_4' and i.quantity > 0 then 4
                            when i.item_key = 'rank_3' and i.quantity > 0 then 3
                            when i.item_key = 'rank_2' and i.quantity > 0 then 2
                            when i.item_key = 'rank_1' and i.quantity > 0 then 1
                            else 0 end) as rank_level
            from dig_weekly_depth w
            join dig_players p on p.chat_id = ? and p.user_id = w.user_id
            join dig_items i on i.chat_id = ? and i.user_id = w.user_id
            where w.week_start = ?
            group by w.user_id, w.depth, p.username, p.full_name
            having rank_level > 0
            order by w.depth desc, rank_level desc, w.user_id asc
            limit ?
            """,
            (DIG_GLOBAL_CHAT_ID, DIG_GLOBAL_CHAT_ID, week_start, max(1, int(limit))),
        ).fetchall()
        return [dict(row) for row in rows]

    def add_dig_expedition_progress(self, chat_id: int, user_id: int, expedition_date: str, depth: int, target: int = 50) -> dict:
        self._conn.execute(
            "insert or ignore into dig_expeditions(chat_id, expedition_date, target) values (?, ?, ?)",
            (chat_id, expedition_date, target),
        )
        self._conn.execute(
            """
            insert into dig_expedition_contributors(chat_id, expedition_date, user_id, depth)
            values (?, ?, ?, ?)
            on conflict(chat_id, expedition_date, user_id) do update set depth = depth + excluded.depth
            """,
            (chat_id, expedition_date, user_id, max(0, int(depth))),
        )
        self._conn.execute(
            """
            update dig_expeditions
            set progress = min(target, progress + ?), completed = case when progress + ? >= target then 1 else completed end
            where chat_id = ? and expedition_date = ?
            """,
            (max(0, int(depth)), max(0, int(depth)), chat_id, expedition_date),
        )
        self._conn.commit()
        return self.get_dig_expedition(chat_id, expedition_date)

    def get_dig_expedition(self, chat_id: int, expedition_date: str) -> dict:
        row = self._conn.execute(
            "select target, progress, completed from dig_expeditions where chat_id = ? and expedition_date = ?",
            (chat_id, expedition_date),
        ).fetchone()
        contributors = self._conn.execute(
            """
            select user_id, depth, rewarded from dig_expedition_contributors
            where chat_id = ? and expedition_date = ? order by depth desc
            """,
            (chat_id, expedition_date),
        ).fetchall()
        return {
            "target": int(row["target"]) if row else 50,
            "progress": int(row["progress"]) if row else 0,
            "completed": bool(row["completed"]) if row else False,
            "contributors": [dict(item) for item in contributors],
        }

    def reward_dig_expedition(self, chat_id: int, expedition_date: str, reward: int) -> list[int]:
        rows = self._conn.execute(
            """
            select user_id from dig_expedition_contributors
            where chat_id = ? and expedition_date = ? and rewarded = 0 and depth > 0
            """,
            (chat_id, expedition_date),
        ).fetchall()
        user_ids = [int(row["user_id"]) for row in rows]
        for user_id in user_ids:
            self.add_dig_coins(DIG_GLOBAL_CHAT_ID, user_id, reward)
        if user_ids:
            self._conn.execute(
                "update dig_expedition_contributors set rewarded = 1 where chat_id = ? and expedition_date = ?",
                (chat_id, expedition_date),
            )
            self._conn.commit()
        return user_ids


def normalize_username(username: str) -> str:
    return username.strip().lstrip("@").lower()


def normalize_trigger(trigger: str) -> str:
    return " ".join(trigger.strip().casefold().split())
