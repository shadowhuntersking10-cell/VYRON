"""Import all models so SQLAlchemy metadata is complete."""
from app.models.base import TimestampMixin  # noqa: F401
from app.models.users import Role, TelegramUser, User, UserRole, UserSession  # noqa: F401
from app.models.catalog import (  # noqa: F401
    Game,
    GameCategory,
    GameField,
    Product,
    ProductVariant,
)
from app.models.commerce import (  # noqa: F401
    Coupon,
    CouponUsage,
    Order,
    OrderItem,
    Payment,
    PaymentTransaction,
    Promotion,
    Refund,
)
from app.models.supply import Supplier, SupplierOrder, SupplierProduct  # noqa: F401
from app.models.marketplace import (  # noqa: F401
    MarketplaceCategory,
    MarketplaceListing,
    MarketplaceListingImage,
    Seller,
    SellerBalance,
    SellerPayout,
)
from app.models.donations import Donation, DonationPreset, DonationProfile  # noqa: F401
from app.models.finance import (  # noqa: F401
    Favorite,
    Notification,
    RevenueLedger,
    Review,
    Wallet,
    WalletTransaction,
)
from app.models.system import AuditLog, Media, Setting, SupportMessage, SupportTicket  # noqa: F401
