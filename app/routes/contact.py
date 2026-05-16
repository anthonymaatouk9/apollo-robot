from flask import Blueprint, request, jsonify
from app import db
from app.models import ContactMessage

contact_bp = Blueprint("contact", __name__)


@contact_bp.route("/send", methods=["POST"])
def send_message():
    data = request.get_json()
    name    = data.get("name", "").strip()
    email   = data.get("email", "").strip()
    subject = data.get("subject", "").strip()
    message = data.get("message", "").strip()

    if not all([name, email, subject, message]):
        return jsonify({"error": "All fields are required"}), 400

    msg = ContactMessage(name=name, email=email, subject=subject, message=message)
    db.session.add(msg)
    db.session.commit()
    return jsonify({"message": "Message sent successfully"}), 201


@contact_bp.route("/messages", methods=["GET"])
def list_messages():
    from flask_login import current_user
    if not current_user.is_authenticated or current_user.role != "admin":
        return jsonify({"error": "Admin only"}), 403
    msgs = ContactMessage.query.order_by(ContactMessage.created_at.desc()).all()
    return jsonify([m.to_dict() for m in msgs])


@contact_bp.route("/messages/<int:mid>/read", methods=["POST"])
def mark_read(mid):
    from flask_login import current_user
    if not current_user.is_authenticated or current_user.role != "admin":
        return jsonify({"error": "Admin only"}), 403
    msg = ContactMessage.query.get_or_404(mid)
    msg.is_read = True
    db.session.commit()
    return jsonify({"message": "Marked as read"})


@contact_bp.route("/messages/<int:mid>", methods=["DELETE"])
def delete_message(mid):
    from flask_login import current_user
    if not current_user.is_authenticated or current_user.role != "admin":
        return jsonify({"error": "Admin only"}), 403
    msg = ContactMessage.query.get_or_404(mid)
    db.session.delete(msg)
    db.session.commit()
    return jsonify({"message": "Deleted"})
