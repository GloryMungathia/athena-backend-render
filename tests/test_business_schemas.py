import pytest
from pydantic import ValidationError

from models.business import BusinessRole, BusinessType, PayoutNetwork
from models.listing import Stream
from schemas.businesses import BusinessCreate, BusinessUpdate, DecisionReason
from schemas.locations import LocationCreate
from tests.factories import location_payload


def business_data(**changes):
    data = {
        "business_legal_name": "  Nairobi   Timber Works Ltd ",
        "business_role": "SUPPLIER",
        "business_type": "BUSINESS",
        "location": location_payload(),
        "streams": ["SAWDUST", "SAWDUST", "GLASS"],
        "contact_email": "info@nairobitimber.co.ke",
    }
    data.update(changes)
    return data


def test_business_create_trims_extra_spaces_and_removes_repeated_streams():
    business = BusinessCreate(**business_data())
    assert business.business_legal_name == "Nairobi Timber Works Ltd"
    assert business.streams == [Stream.SAWDUST, Stream.GLASS]


def test_business_create_rejects_html_in_legal_name():
    with pytest.raises(ValidationError):
        BusinessCreate(**business_data(business_legal_name="<script>x</script>"))


def test_business_create_allows_consumer_type_only_for_buyers():
    with pytest.raises(ValidationError):
        BusinessCreate(**business_data(business_type="CONSUMER"))
    buyer = BusinessCreate(
        **business_data(business_role="BUYER", business_type="CONSUMER")
    )
    assert buyer.business_role == BusinessRole.BUYER
    assert buyer.business_type == BusinessType.CONSUMER


def test_business_create_rejects_supplier_kind_for_non_suppliers():
    with pytest.raises(ValidationError):
        BusinessCreate(**business_data(business_role="BUYER", supplier_kind="DEALER"))


def test_business_create_rejects_unknown_stream():
    with pytest.raises(ValidationError):
        BusinessCreate(**business_data(streams=["METAL"]))


@pytest.mark.parametrize(
    "raw", ["0712345678", "+254 712 345 678", "254712345678", "712-345-678"]
)
def test_kenyan_mobile_contact_phone_in_any_format_is_saved_as_plus_254(raw):
    business = BusinessCreate(**business_data(contact_phone=raw))
    assert business.contact_phone == "+254712345678"


def test_kenyan_01_mobile_contact_phone_is_saved_as_plus_254():
    business = BusinessCreate(**business_data(contact_phone="0110 123 456"))
    assert business.contact_phone == "+254110123456"


def test_kenyan_landline_with_leading_zero_is_saved_as_plus_254():
    business = BusinessCreate(**business_data(contact_phone="020 2345678"))
    assert business.contact_phone == "+254202345678"


def test_contact_phone_with_letters_is_rejected():
    with pytest.raises(ValidationError):
        BusinessCreate(**business_data(contact_phone="12ab"))


@pytest.mark.parametrize("raw", ["0722123456", "+254 722 123 456", "0110123456"])
def test_kenyan_mpesa_payout_phone_is_saved_as_plus_254(raw):
    business = BusinessCreate(**business_data(payout_phone=raw, payout_network="MPESA"))
    assert business.payout_phone == "+254" + raw.replace(" ", "")[-9:]
    assert business.payout_network == PayoutNetwork.MPESA


@pytest.mark.parametrize("raw", ["+250788123456", "0202345678", "12345"])
def test_payout_phone_that_is_not_a_kenyan_mobile_is_rejected(raw):
    with pytest.raises(ValidationError, match="enter an M-Pesa number"):
        BusinessCreate(**business_data(payout_phone=raw, payout_network="MPESA"))


def test_payout_phone_without_network_is_rejected():
    with pytest.raises(ValidationError):
        BusinessCreate(**business_data(payout_phone="0722123456"))


def test_old_mtn_payout_network_is_rejected():
    with pytest.raises(ValidationError):
        BusinessCreate(
            **business_data(payout_phone="0722123456", payout_network="MTN_MOMO")
        )


def test_business_update_keeps_only_the_fields_that_were_sent():
    update = BusinessUpdate(display_name="Nairobi Timber")
    assert update.model_dump(exclude_unset=True) == {"display_name": "Nairobi Timber"}


def test_decision_reason_must_be_at_least_5_characters():
    with pytest.raises(ValidationError):
        DecisionReason(reason="  no ")
    assert DecisionReason(reason="Documents unclear").reason == "Documents unclear"


def test_location_create_uppercases_osm_type_and_rounds_coordinates():
    location = LocationCreate(
        osm_type="way",
        osm_id=42,
        name="Westlands",
        display_name="Westlands, Nairobi",
        latitude=-1.2675004,
        longitude=36.8108004,
        sub_county="Westlands",
        county="Nairobi",
    )
    assert location.osm_type.value == "WAY"
    assert str(location.latitude) == "-1.267500"


def test_location_create_rejects_latitude_above_90():
    with pytest.raises(ValidationError):
        LocationCreate(
            osm_type="node",
            osm_id=1,
            name="Nowhere",
            display_name="Nowhere",
            latitude=95,
            longitude=36,
            sub_county="Westlands",
            county="Nairobi",
        )
