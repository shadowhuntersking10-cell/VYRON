"""Canonical enumerations for VYRON.

Stored as VARCHAR in MySQL (validated application-side) for portability across
MySQL 5.7 / 8.x / MariaDB and zero-cost migrations when adding values.
"""

from __future__ import annotations

from enum import Enum


class StrEnum(str, Enum):
    def __str__(self) -> str:  # pragma: no cover
        return self.value


class UserRole(StrEnum):
    USER = "USER"
    SELLER = "SELLER"
    SUPPORT = "SUPPORT"
    MODERATOR = "MODERATOR"
    FINANCE = "FINANCE"
    ADMIN = "ADMIN"
    SUPER_ADMIN = "SUPER_ADMIN"


# Roles ordered by privilege for "at least" checks
ROLE_LEVELS = {
    UserRole.USER: 0,
    UserRole.SELLER: 1,
    UserRole.SUPPORT: 2,
    UserRole.MODERATOR: 3,
    UserRole.FINANCE: 4,
    UserRole.ADMIN: 5,
    UserRole.SUPER_ADMIN: 6,
}

STAFF_ROLES = {UserRole.SUPPORT, UserRole.MODERATOR, UserRole.FINANCE, UserRole.ADMIN, UserRole.SUPER_ADMIN}
ADMIN_ROLES = {UserRole.ADMIN, UserRole.SUPER_ADMIN}


class UserStatus(StrEnum):
    ACTIVE = "ACTIVE"
    DISABLED = "DISABLED"
    SUSPENDED = "SUSPENDED"


class GameStatus(StrEnum):
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"
    COMING_SOON = "COMING_SOON"


class ProductType(StrEnum):
    TOPUP = "TOPUP"
    GIFT_CARD = "GIFT_CARD"
    GAME_KEY = "GAME_KEY"
    DIGITAL_ITEM = "DIGITAL_ITEM"
    SUBSCRIPTION = "SUBSCRIPTION"
    DONATION = "DONATION"
    OTHER = "OTHER"


class OrderStatus(StrEnum):
    CREATED = "CREATED"
    PAYMENT_PENDING = "PAYMENT_PENDING"
    PAID = "PAID"
    PROCESSING = "PROCESSING"
    DELIVERING = "DELIVERING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    MANUAL_REVIEW = "MANUAL_REVIEW"
    REFUND_PENDING = "REFUND_PENDING"
    REFUNDED = "REFUNDED"
    CANCELLED = "CANCELLED"


class PaymentStatus(StrEnum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    PAID = "PAID"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    EXPIRED = "EXPIRED"
    REFUNDED = "REFUNDED"
    PARTIALLY_REFUNDED = "PARTIALLY_REFUNDED"


class PaymentPurpose(StrEnum):
    ORDER = "ORDER"
    DONATION = "DONATION"
    PROMOTION = "PROMOTION"
    SUBSCRIPTION = "SUBSCRIPTION"
    MARKETPLACE_ORDER = "MARKETPLACE_ORDER"


class RefundStatus(StrEnum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    REJECTED = "REJECTED"


class TransactionType(StrEnum):
    PAYMENT_IN = "PAYMENT_IN"
    REFUND_OUT = "REFUND_OUT"
    SUPPLIER_COST = "SUPPLIER_COST"
    MARKETPLACE_COMMISSION = "MARKETPLACE_COMMISSION"
    DONATION_FEE = "DONATION_FEE"
    SERVICE_FEE = "SERVICE_FEE"
    PAYMENT_FEE = "PAYMENT_FEE"
    SELLER_CREDIT = "SELLER_CREDIT"
    SELLER_PAYOUT = "SELLER_PAYOUT"
    PROMOTION_PURCHASE = "PROMOTION_PURCHASE"
    SUBSCRIPTION_PURCHASE = "SUBSCRIPTION_PURCHASE"


class RevenueStream(StrEnum):
    GROSS_REVENUE = "GROSS_REVENUE"
    TOPUP_MARGIN = "TOPUP_MARGIN"
    SUPPLIER_COST = "SUPPLIER_COST"
    MARKETPLACE_COMMISSION = "MARKETPLACE_COMMISSION"
    DONATION_FEE = "DONATION_FEE"
    SERVICE_FEE = "SERVICE_FEE"
    PAYMENT_FEE = "PAYMENT_FEE"
    PROMOTION_FEE = "PROMOTION_FEE"
    SUBSCRIPTION_FEE = "SUBSCRIPTION_FEE"
    REFUND = "REFUND"
    SELLER_PAYOUT = "SELLER_PAYOUT"
    NET_REVENUE = "NET_REVENUE"


class SupplierStatus(StrEnum):
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"
    ERROR = "ERROR"
    SYNCING = "SYNCING"


class SupplierOrderStatus(StrEnum):
    PENDING = "PENDING"
    SUBMITTED = "SUBMITTED"
    PROCESSING = "PROCESSING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    UNKNOWN = "UNKNOWN"
    CANCELLED = "CANCELLED"
    REFUNDED = "REFUNDED"


class SupplierAttemptOutcome(StrEnum):
    SUCCESS = "SUCCESS"
    FAILURE = "FAILURE"
    UNKNOWN = "UNKNOWN"
    TIMEOUT = "TIMEOUT"
    VALIDATION_ERROR = "VALIDATION_ERROR"
    NOT_CONFIGURED = "NOT_CONFIGURED"


class ListingStatus(StrEnum):
    DRAFT = "DRAFT"
    PENDING_REVIEW = "PENDING_REVIEW"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    SUSPENDED = "SUSPENDED"
    SOLD = "SOLD"


class ListingDeliveryType(StrEnum):
    INSTANT = "INSTANT"
    MANUAL = "MANUAL"
    ACCOUNT = "ACCOUNT"          # legitimate digital account listings only
    GIFT_CARD = "GIFT_CARD"
    GAME_KEY = "GAME_KEY"


class SellerVerificationStatus(StrEnum):
    UNVERIFIED = "UNVERIFIED"
    PENDING = "PENDING"
    VERIFIED = "VERIFIED"
    REJECTED = "REJECTED"


class SellerStatus(StrEnum):
    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"


class SellerOrderStatus(StrEnum):
    PENDING_PAYMENT = "PENDING_PAYMENT"
    PAID = "PAID"
    DELIVERED = "DELIVERED"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"
    REFUNDED = "REFUNDED"
    DISPUTED = "DISPUTED"


class BalanceTxType(StrEnum):
    HOLD = "HOLD"                # earnings enter pending
    RELEASE = "RELEASE"          # pending -> available after holding period
    WITHDRAW = "WITHDRAW"        # payout request reserves available
    REVERSAL = "REVERSAL"        # refund/chargeback claw-back
    PAYOUT = "PAYOUT"            # payout completed
    ADJUSTMENT = "ADJUSTMENT"    # admin correction (audited)


class PayoutStatus(StrEnum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    REJECTED = "REJECTED"


class PromotionKind(StrEnum):
    FEATURED = "FEATURED"
    HOMEPAGE = "HOMEPAGE"
    CATEGORY = "CATEGORY"
    SEARCH = "SEARCH"


class DonationStatus(StrEnum):
    PENDING = "PENDING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    REFUNDED = "REFUNDED"


class CouponType(StrEnum):
    PERCENTAGE = "PERCENTAGE"
    FIXED = "FIXED"


class NotificationType(StrEnum):
    REGISTRATION = "REGISTRATION"
    EMAIL_VERIFIED = "EMAIL_VERIFIED"
    PAYMENT_SUCCESS = "PAYMENT_SUCCESS"
    PAYMENT_FAILED = "PAYMENT_FAILED"
    ORDER_PROCESSING = "ORDER_PROCESSING"
    ORDER_DELIVERING = "ORDER_DELIVERING"
    ORDER_COMPLETED = "ORDER_COMPLETED"
    ORDER_FAILED = "ORDER_FAILED"
    REFUND = "REFUND"
    PAYOUT = "PAYOUT"
    SUPPORT_RESPONSE = "SUPPORT_RESPONSE"
    LISTING_REVIEWED = "LISTING_REVIEWED"
    SELLER_ORDER = "SELLER_ORDER"
    DONATION_RECEIVED = "DONATION_RECEIVED"
    SECURITY = "SECURITY"
    MARKETING = "MARKETING"


class EmailStatus(StrEnum):
    QUEUED = "QUEUED"
    SENT = "SENT"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"          # e.g. SMTP not configured — visible, never faked


class TicketStatus(StrEnum):
    OPEN = "OPEN"
    IN_PROGRESS = "IN_PROGRESS"
    WAITING_USER = "WAITING_USER"
    RESOLVED = "RESOLVED"
    CLOSED = "CLOSED"


class TicketPriority(StrEnum):
    LOW = "LOW"
    NORMAL = "NORMAL"
    HIGH = "HIGH"
    URGENT = "URGENT"


class RiskLevel(StrEnum):
    LOW = "LOW"            # 0-30
    MEDIUM = "MEDIUM"      # 31-60
    HIGH = "HIGH"          # 61-80
    CRITICAL = "CRITICAL"  # 81-100


class FraudEventType(StrEnum):
    FAILED_PAYMENTS = "FAILED_PAYMENTS"
    RAPID_ORDERS = "RAPID_ORDERS"
    UNUSUAL_FREQUENCY = "UNUSUAL_FREQUENCY"
    REFUND_ABUSE = "REFUND_ABUSE"
    SUSPICIOUS_PATTERN = "SUSPICIOUS_PATTERN"
    SUPPLIER_ABUSE = "SUPPLIER_ABUSE"
    MANUAL = "MANUAL"


class SubscriptionStatus(StrEnum):
    PENDING_PAYMENT = "PENDING_PAYMENT"
    ACTIVE = "ACTIVE"
    EXPIRED = "EXPIRED"
    CANCELLED = "CANCELLED"


class QueueName(StrEnum):
    SUPPLIER_ORDERS = "supplier-orders"
    SUPPLIER_STATUS = "supplier-status"
    PAYMENTS = "payments"
    NOTIFICATIONS = "notifications"
    EMAILS = "emails"
    TELEGRAM = "telegram"
    FRAUD = "fraud"
    REFUNDS = "refunds"
    PAYOUTS = "payouts"


def risk_level_for_score(score: int) -> RiskLevel:
    if score <= 30:
        return RiskLevel.LOW
    if score <= 60:
        return RiskLevel.MEDIUM
    if score <= 80:
        return RiskLevel.HIGH
    return RiskLevel.CRITICAL
