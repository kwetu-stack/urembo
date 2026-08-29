from flask import Blueprint, render_template

retailer_verification_bp = Blueprint(
    "retailer_verification",
    __name__
)

@retailer_verification_bp.route("/retailer-verification")
def retailer_verification():
    return render_template("retailer_verification.html")