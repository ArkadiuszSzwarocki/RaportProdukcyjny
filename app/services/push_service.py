"""Push Notification Service using Web Push (VAPID).

Handles sending push notifications to subscribed devices.
Integrates with pywebpush library.
"""

import json
import logging

logger = logging.getLogger(__name__)


def _get_vapid_config():
    """Return VAPID keys from app config. Returns (private_key, claims) or (None, None)."""
    try:
        from app.config import VAPID_PRIVATE_KEY, VAPID_CLAIMS_EMAIL
        if not VAPID_PRIVATE_KEY:
            return None, None
        claims = {"sub": f"mailto:{VAPID_CLAIMS_EMAIL}"}
        return VAPID_PRIVATE_KEY, claims
    except Exception as e:
        logger.warning("[PUSH] Failed to load VAPID config: %s", e)
        return None, None


def send_push_notification(subscription_info: dict, title: str, body: str, url: str = '/') -> bool:
    """Send a single Web Push notification to one device subscription.

    Args:
        subscription_info: Dict with keys 'endpoint', 'keys' (with 'p256dh' and 'auth')
        title: Notification title
        body: Notification body text
        url: URL to open when notification is clicked

    Returns:
        True if sent successfully, False otherwise
    """
    private_key, claims = _get_vapid_config()
    if not private_key:
        logger.warning("[PUSH] VAPID not configured — skipping push notification")
        return False

    try:
        from pywebpush import webpush, WebPushException

        payload = json.dumps({
            "title": title,
            "body": body,
            "url": url,
            "icon": "/static/agro_logo.png",
        })

        webpush(
            subscription_info=subscription_info,
            data=payload,
            vapid_private_key=private_key,
            vapid_claims=claims,
        )
        return True

    except Exception as exc:
        # Import here to avoid circular at module load time
        try:
            from pywebpush import WebPushException
            if isinstance(exc, WebPushException):
                status_code = exc.response.status_code if exc.response is not None else None
                if status_code in (404, 410):
                    # Subscription expired/revoked — caller should delete it
                    logger.info("[PUSH] Subscription gone (%s) for endpoint: %s",
                                status_code, subscription_info.get('endpoint', '')[:60])
                    return False
                logger.warning("[PUSH] WebPushException (status=%s): %s", status_code, exc)
                return False
        except ImportError:
            pass
        logger.error("[PUSH] Unexpected error sending push: %s", exc)
        return False


def send_push_to_role(rola: str, title: str, body: str, url: str = '/') -> int:
    """Send a push notification to all subscribed devices for a given role.

    Args:
        rola: Role name (e.g. 'planista', 'admin', 'masteradmin')
        title: Notification title
        body: Notification body
        url: Link to open on click

    Returns:
        Number of successfully sent pushes
    """
    try:
        from app.db import get_push_subscriptions_for_role, delete_push_subscription

        subscriptions = get_push_subscriptions_for_role(rola)
        if not subscriptions:
            return 0

        sent = 0
        for sub in subscriptions:
            subscription_info = {
                "endpoint": sub["endpoint"],
                "keys": {
                    "p256dh": sub["p256dh"],
                    "auth": sub["auth"],
                },
            }
            ok = send_push_notification(subscription_info, title, body, url)
            if ok:
                sent += 1
            else:
                # Try to detect and clean gone endpoints
                _maybe_delete_gone_subscription(sub["endpoint"])

        logger.info("[PUSH] Sent %d/%d push notifications for role '%s'", sent, len(subscriptions), rola)
        return sent

    except Exception as e:
        logger.error("[PUSH] Error in send_push_to_role('%s'): %s", rola, e)
        return 0


def send_push_to_login(login: str, title: str, body: str, url: str = '/') -> int:
    """Send a push notification to all subscribed devices for a specific login.

    Args:
        login: Username to target
        title: Notification title
        body: Notification body
        url: Link to open on click

    Returns:
        Number of successfully sent pushes
    """
    try:
        from app.db import get_push_subscriptions_for_login

        subscriptions = get_push_subscriptions_for_login(login)
        if not subscriptions:
            return 0

        sent = 0
        for sub in subscriptions:
            subscription_info = {
                "endpoint": sub["endpoint"],
                "keys": {
                    "p256dh": sub["p256dh"],
                    "auth": sub["auth"],
                },
            }
            ok = send_push_notification(subscription_info, title, body, url)
            if ok:
                sent += 1
            else:
                _maybe_delete_gone_subscription(sub["endpoint"])

        logger.info("[PUSH] Sent %d/%d push notifications for login '%s'", sent, len(subscriptions), login)
        return sent

    except Exception as e:
        logger.error("[PUSH] Error in send_push_to_login('%s'): %s", login, e)
        return 0


def send_push_to_roles(roles: list, title: str, body: str, url: str = '/') -> int:
    """Send push notifications to multiple roles (deduplicating user subscriptions).

    Args:
        roles: List of role names
        title: Notification title
        body: Notification body
        url: Link to open on click

    Returns:
        Total number of successfully sent pushes
    """
    try:
        from app.db import get_push_subscriptions_for_roles

        subscriptions = get_push_subscriptions_for_roles(roles)
        if not subscriptions:
            return 0

        sent = 0
        for sub in subscriptions:
            subscription_info = {
                "endpoint": sub["endpoint"],
                "keys": {
                    "p256dh": sub["p256dh"],
                    "auth": sub["auth"],
                },
            }
            ok = send_push_notification(subscription_info, title, body, url)
            if ok:
                sent += 1
            else:
                _maybe_delete_gone_subscription(sub["endpoint"])

        logger.info("[PUSH] Sent %d/%d push notifications for roles %s", sent, len(subscriptions), roles)
        return sent

    except Exception as e:
        logger.error("[PUSH] Error in send_push_to_roles(%s): %s", roles, e)
        return 0


def _maybe_delete_gone_subscription(endpoint: str) -> None:
    """Attempt to delete a subscription that appears to be expired."""
    try:
        from app.db import delete_push_subscription
        delete_push_subscription(endpoint)
    except Exception:
        pass
