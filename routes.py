"""All HTTP routes (one blueprint to keep the project easy to follow)."""
from flask import (Blueprint, abort, current_app, flash, jsonify, redirect, render_template,
                   request, url_for)
from werkzeug.utils import secure_filename

from models import activity, appointments, clean_text, doctors, parse_page, settings
from services import ai_service, csv_import

bp = Blueprint("main", __name__)


def _per_page():
    return current_app.config["PER_PAGE"]


def _appointment_or_404(appointment_id):
    appt = appointments.get(appointment_id)
    if appt is None:
        abort(404)
    return appt


# ------------------------------------------------------------------ overview
@bp.get("/")
def overview():
    return render_template("overview.html", stats=appointments.stats(),
                           doctor_count=doctors.count(), upcoming=appointments.upcoming(),
                           recent=activity.recent(8))


# ------------------------------------------------------------------ appointments
@bp.get("/appointments")
def appointment_list():
    args = request.args
    rows, meta = appointments.search(args.get("q", ""), args.get("status", ""),
                                     args.get("date_from", ""), args.get("date_to", ""),
                                     parse_page(args.get("page")), _per_page())
    filters = {k: args.get(k, "") for k in ("q", "status", "date_from", "date_to")}
    return render_template("appointments.html", rows=rows, meta=meta, filters=filters,
                           statuses=appointments.STATUSES)


@bp.route("/appointments/new", methods=["GET", "POST"])
def appointment_new():
    if request.method == "POST":
        clean, errors = appointments.validate(request.form)
        if not errors:
            appt_id = appointments.create(clean)
            activity.log("appointment_created", f"Appointment request #{appt_id} created.")
            flash("Appointment request saved as Pending.", "success")
            return redirect(url_for("main.appointment_detail", appointment_id=appt_id))
        flash("Fix the highlighted fields and save again.", "error")
        return render_template("appointment_form.html", form=clean, errors=errors, appt=None,
                               statuses=appointments.STATUSES), 422
    return render_template("appointment_form.html", form={}, errors={}, appt=None,
                           statuses=appointments.STATUSES)


@bp.get("/appointments/<int:appointment_id>")
def appointment_detail(appointment_id):
    return render_template("appointment_detail.html", appt=_appointment_or_404(appointment_id))


@bp.route("/appointments/<int:appointment_id>/edit", methods=["GET", "POST"])
def appointment_edit(appointment_id):
    appt = _appointment_or_404(appointment_id)
    if request.method == "POST":
        clean, errors = appointments.validate(request.form, require_status=True)
        if errors:
            flash("Fix the highlighted fields and save again.", "error")
            return render_template("appointment_form.html", form=clean, errors=errors, appt=appt,
                                   statuses=appointments.STATUSES), 422
        changed = [f for f in appointments.EDITABLE_FIELDS if clean[f] != appt[f]]
        status_changed = clean["status"] != appt["status"]
        if not changed and not status_changed:
            flash("No changes to save.", "info")
            return redirect(url_for("main.appointment_detail", appointment_id=appointment_id))
        appointments.update(appointment_id, clean)
        if changed:
            labels = ", ".join(f.replace("_", " ") for f in changed)
            activity.log("appointment_updated", f"Appointment request #{appointment_id} updated ({labels}).")
        if status_changed:
            activity.log("status_changed", f"Appointment request #{appointment_id} status changed "
                                           f"from {appt['status']} to {clean['status']}.")
        flash("Changes saved.", "success")
        return redirect(url_for("main.appointment_detail", appointment_id=appointment_id))
    form = {k: appt[k] for k in (*appointments.EDITABLE_FIELDS, "status")}
    return render_template("appointment_form.html", form=form, errors={}, appt=appt,
                           statuses=appointments.STATUSES)


@bp.post("/appointments/<int:appointment_id>/status")
def appointment_status(appointment_id):
    """Quick, non-destructive transitions. Cancelling goes through a confirmation page."""
    appt = _appointment_or_404(appointment_id)
    new_status = clean_text(request.form.get("status"))
    if new_status not in ("Pending", "Confirmed"):
        abort(400)
    if new_status != appt["status"]:
        appointments.set_status(appointment_id, new_status)
        activity.log("status_changed", f"Appointment request #{appointment_id} status changed "
                                       f"from {appt['status']} to {new_status}.")
        flash(f"Request #{appointment_id} is now {new_status}.", "success")
    return redirect(request.form.get("next") if request.form.get("next", "").startswith("/")
                    and not request.form.get("next", "").startswith("//")
                    else url_for("main.appointment_list"))


@bp.route("/appointments/<int:appointment_id>/cancel", methods=["GET", "POST"])
def appointment_cancel(appointment_id):
    appt = _appointment_or_404(appointment_id)
    if request.method == "POST":
        if appt["status"] != "Cancelled":
            appointments.set_status(appointment_id, "Cancelled")
            activity.log("appointment_cancelled", f"Appointment request #{appointment_id} cancelled.")
            flash(f"Request #{appointment_id} cancelled. The record is kept.", "success")
        return redirect(url_for("main.appointment_detail", appointment_id=appointment_id))
    return render_template("confirm_action.html", appt=appt, action="cancel")


@bp.route("/appointments/<int:appointment_id>/delete", methods=["GET", "POST"])
def appointment_delete(appointment_id):
    appt = _appointment_or_404(appointment_id)
    if request.method == "POST":
        appointments.delete(appointment_id)
        activity.log("appointment_deleted", f"Appointment request #{appointment_id} deleted.")
        flash(f"Request #{appointment_id} permanently deleted.", "success")
        return redirect(url_for("main.appointment_list"))
    return render_template("confirm_action.html", appt=appt, action="delete")


# ------------------------------------------------------------------ doctors
def _render_doctors(report=None, status=200):
    args = request.args
    rows, meta = doctors.search(args.get("q", ""), args.get("specialty", ""), args.get("city", ""),
                                parse_page(args.get("page")), _per_page())
    filters = {k: args.get(k, "") for k in ("q", "specialty", "city")}
    return render_template("doctors.html", rows=rows, meta=meta, filters=filters,
                           specialties=doctors.distinct("specialty"), cities=doctors.distinct("city"),
                           report=report, total_doctors=doctors.count()), status


@bp.get("/doctors")
def doctor_list():
    return _render_doctors()


@bp.post("/doctors/import")
def doctor_import():
    upload = request.files.get("file")
    name = secure_filename(upload.filename)[:80] if upload and upload.filename else ""
    report = csv_import.ImportReport(filename=name)
    if not name:
        report.file_error = "Choose a CSV file to import."
        return _render_doctors(report, 400)
    if not name.lower().endswith(".csv"):
        report.file_error = "Only .csv files are accepted."
        return _render_doctors(report, 400)

    limit = current_app.config["MAX_CONTENT_LENGTH"]
    data = upload.stream.read(limit + 1)
    if len(data) > limit:
        abort(413)
    report = csv_import.parse_csv(data, name, doctors.existing_keys(),
                                  current_app.config["MAX_CSV_ROWS"])
    if report.file_error:
        activity.log("csv_import_failed", f"CSV import rejected ({name}): {report.file_error}"[:300])
        return _render_doctors(report, 422)

    csv_import.apply_import(report)
    activity.log("csv_import",
                 f"CSV import of {name}: {report.imported} imported, "
                 f"{len(report.duplicates)} duplicate(s) skipped, {len(report.errors)} row(s) rejected.")
    if report.imported:
        flash(f"Imported {report.imported} record(s).", "success")
    else:
        flash("No records were imported. See the summary below.", "info")
    return _render_doctors(report, 200)


# ------------------------------------------------------------------ AI assistant
@bp.get("/assistant")
def assistant():
    return render_template("assistant.html", ai=ai_service.status(),
                           confirmed=appointments.confirmed_for_drafting())


def _json_field(name, max_len, required=True):
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        abort(400)
    value = clean_text(payload.get(name))
    if required and not value:
        return None, f"Enter some text for '{name}'."
    if len(value) > max_len:
        return None, f"Keep '{name}' to {max_len} characters or fewer."
    return value, None


def _bad(message):
    return jsonify(error=message), 422


@bp.post("/assistant/categorize")
def assistant_categorize():
    enquiry, err = _json_field("enquiry", 1000)
    if err:
        return _bad(err)
    result = ai_service.categorize(enquiry, settings.clinic_name())
    activity.log("ai_request", f"AI categorisation requested (source: {result['source']}).")
    return jsonify(result)


@bp.post("/assistant/respond")
def assistant_respond():
    enquiry, err = _json_field("enquiry", 1000)
    if err:
        return _bad(err)
    facts, err = _json_field("facts", 1000, required=False)
    if err:
        return _bad(err)
    result = ai_service.draft_response(enquiry, facts, settings.clinic_name())
    activity.log("ai_request", f"AI response draft requested (source: {result['source']}).")
    return jsonify(result)


@bp.post("/assistant/appointment-message")
def assistant_appointment_message():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        abort(400)
    kind = payload.get("kind")
    if kind not in ("confirmation", "reminder"):
        return _bad("Choose confirmation or reminder.")
    try:
        appt_id = int(payload.get("appointment_id"))
    except (TypeError, ValueError):
        return _bad("Choose an appointment.")
    appt = appointments.get(appt_id)
    if appt is None:
        return _bad("That appointment no longer exists.")
    if appt["status"] != "Confirmed":
        return _bad("Only Confirmed appointments can have a confirmation or reminder drafted.")
    result = ai_service.draft_appointment_message(appt, kind, settings.clinic_name())
    activity.log("ai_request", f"AI appointment {kind} draft requested for request #{appt_id} "
                               f"(source: {result['source']}).")
    return jsonify(result)


# ------------------------------------------------------------------ activity + settings
@bp.get("/activity")
def activity_log():
    rows, meta = activity.page(parse_page(request.args.get("page")))
    return render_template("activity.html", rows=rows, meta=meta)


@bp.route("/settings", methods=["GET", "POST"])
def settings_page():
    error = None
    if request.method == "POST":
        name = clean_text(request.form.get("clinic_name"))
        if not name:
            error = "Enter a clinic name."
        elif len(name) > 80:
            error = "Keep the clinic name to 80 characters or fewer."
        else:
            settings.set_value("clinic_name", name)
            activity.log("settings_updated", "Clinic display name updated.")
            flash("Settings saved.", "success")
            return redirect(url_for("main.settings_page"))
    return render_template("settings.html", clinic_name=clean_text(request.form.get("clinic_name"))
                           if error else settings.clinic_name(), error=error, ai=ai_service.status(),
                           app_config=current_app.config), (422 if error else 200)
