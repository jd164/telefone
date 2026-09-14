import phonenumbers
from phonenumbers import geocoder, carrier, PhoneNumberType
from app.models.schemas import NormalizedNumberInfo
from app.core.config import settings

# Mapping from PhoneNumberType integer to readable string
NUMBER_TYPE_MAPPING = {
    PhoneNumberType.FIXED_LINE: "FIXED_LINE",
    PhoneNumberType.MOBILE: "MOBILE",
    PhoneNumberType.FIXED_LINE_OR_MOBILE: "FIXED_LINE_OR_MOBILE",
    PhoneNumberType.TOLL_FREE: "TOLL_FREE",
    PhoneNumberType.PREMIUM_RATE: "PREMIUM_RATE",
    PhoneNumberType.SHARED_COST: "SHARED_COST",
    PhoneNumberType.VOIP: "VOIP",
    PhoneNumberType.PERSONAL_NUMBER: "PERSONAL_NUMBER",
    PhoneNumberType.PAGER: "PAGER",
    PhoneNumberType.UAN: "UNIVERSAL_ACCESS",
    PhoneNumberType.VOICEMAIL: "VOICEMAIL",
    PhoneNumberType.UNKNOWN: "UNKNOWN",
}


def normalize_phone_number(raw_input: str, default_country: str = settings.DEFAULT_COUNTRY) -> NormalizedNumberInfo:
    """
    Parses and normalizes any phone string (PT local or international).
    Uses libphonenumber port to validate format, country, and carrier category.
    """
    clean_input = raw_input.strip()

    # Pre-clean input: if user types 00351, transform to +351
    if clean_input.startswith("00") and not clean_input.startswith("000"):
        clean_input = "+" + clean_input[2:]

    try:
        parsed = phonenumbers.parse(clean_input, default_country)
    except phonenumbers.NumberParseException:
        # Try prepending '+' if it might be an international number with digits only
        try:
            parsed = phonenumbers.parse("+" + clean_input, None)
        except phonenumbers.NumberParseException as exc:
            # Fallback for completely unparseable input
            return NormalizedNumberInfo(
                raw_input=raw_input,
                e164=clean_input,
                national_format=clean_input,
                international_format=clean_input,
                country_code=0,
                country_name="Unknown",
                region_code="",
                line_type="INVALID",
                is_valid=False,
                is_possible=False,
                carrier_name=None,
            )

    is_valid = phonenumbers.is_valid_number(parsed)
    is_possible = phonenumbers.is_possible_number(parsed)

    e164_str = phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)
    national_str = phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.NATIONAL)
    international_str = phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.INTERNATIONAL)

    # Country & Region
    region_code = phonenumbers.region_code_for_number(parsed) or ""
    country_name = geocoder.country_name_for_number(parsed, "pt") or geocoder.country_name_for_number(parsed, "en") or region_code

    # Carrier & Line type
    num_type = phonenumbers.number_type(parsed)
    line_type_str = NUMBER_TYPE_MAPPING.get(num_type, "UNKNOWN")

    carrier_name = carrier.name_for_number(parsed, "pt") or carrier.name_for_number(parsed, "en") or None

    return NormalizedNumberInfo(
        raw_input=raw_input,
        e164=e164_str,
        national_format=national_str,
        international_format=international_str,
        country_code=parsed.country_code,
        country_name=country_name,
        region_code=region_code,
        line_type=line_type_str,
        is_valid=is_valid,
        is_possible=is_possible,
        carrier_name=carrier_name,
    )
