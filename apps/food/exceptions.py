from shared.exceptions import DomainError


class FoodError(DomainError):
    code = "food_error"


class FoodCustomerNotFoundError(FoodError):
    code = "food_customer_not_found"


class FoodProductNotFoundError(FoodError):
    code = "food_product_not_found"


class FoodOrderNotFoundError(FoodError):
    code = "food_order_not_found"


class FoodDuplicateIdempotencyError(FoodError):
    code = "food_duplicate_idempotency"


class FoodInvalidOrderError(FoodError):
    code = "food_invalid_order"


class FoodInsufficientStockError(FoodError):
    code = "food_insufficient_stock"


class FoodInvalidTransitionError(FoodError):
    code = "food_invalid_transition"


class FoodPaymentError(FoodError):
    code = "food_payment_error"


class FoodPaymentProviderError(FoodPaymentError):
    code = "food_payment_provider_error"


class FoodPaymentEmailRequiredError(FoodPaymentError):
    code = "food_payment_email_required"


class FoodPaymentMethodNotAllowedError(FoodPaymentError):
    code = "food_payment_method_not_allowed"


class FoodPaymentCardTokenRequiredError(FoodPaymentError):
    code = "food_payment_card_token_required"
