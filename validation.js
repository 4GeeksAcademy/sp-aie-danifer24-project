(function () {
    "use strict";

    const form = document.getElementById("form-registro");
    if (!form) return;

    const formMessage = document.getElementById("form-mensaje");
    const fields = Array.from(form.querySelectorAll("input, select, textarea")).filter((field) => {
        return !["submit", "reset", "button"].includes(field.type);
    });

    const fieldClassState = {
        valid: ["border-emerald-500", "focus:border-emerald-500", "focus:ring-emerald-200"],
        invalid: ["border-red-500", "focus:border-red-500", "focus:ring-red-200"]
    };
    let isSubmitReset = false;

    function setFormMessage(type, text) {
        formMessage.classList.remove(
            "hidden",
            "border-red-200",
            "bg-red-50",
            "text-red-700",
            "border-emerald-200",
            "bg-emerald-50",
            "text-emerald-700"
        );

        if (type === "error") {
            formMessage.classList.add("border-red-200", "bg-red-50", "text-red-700");
        } else if (type === "success") {
            formMessage.classList.add("border-emerald-200", "bg-emerald-50", "text-emerald-700");
        } else {
            formMessage.classList.add("hidden");
        }

        formMessage.textContent = text || "";
    }

    function ensureFieldErrorElement(field) {
        const key = field.id || field.name;
        const errorId = "error-" + key;
        let errorElement = document.getElementById(errorId);

        if (errorElement) return errorElement;

        errorElement = document.createElement("p");
        errorElement.id = errorId;
        errorElement.className = "mt-1 hidden text-xs font-medium text-red-600";

        if (field.type === "checkbox") {
            const wrapper = field.closest("label") || field.parentElement;
            wrapper.insertAdjacentElement("afterend", errorElement);
        } else {
            field.insertAdjacentElement("afterend", errorElement);
        }

        const describedBy = (field.getAttribute("aria-describedby") || "").trim();
        const ids = describedBy ? describedBy.split(/\s+/) : [];
        if (!ids.includes(errorId)) {
            ids.push(errorId);
            field.setAttribute("aria-describedby", ids.join(" "));
        }

        return errorElement;
    }

    function clearVisualState(field) {
        field.classList.remove(...fieldClassState.valid, ...fieldClassState.invalid);
        field.removeAttribute("title");
        field.setCustomValidity("");
        field.setAttribute("aria-invalid", "false");

        const errorElement = ensureFieldErrorElement(field);
        errorElement.textContent = "";
        errorElement.classList.add("hidden");
    }

    function getErrorMessage(field) {
        const validity = field.validity;

        if (validity.valueMissing) return "Este campo es obligatorio.";
        if (validity.typeMismatch && field.type === "email") return "Introduce un email válido.";
        if (validity.typeMismatch) return "El formato del campo no es válido.";
        if (validity.patternMismatch && field.id === "telefono") return "Introduce un teléfono válido (7 a 20 caracteres).";
        if (validity.patternMismatch) return "El formato ingresado no coincide con el esperado.";
        if (validity.tooShort) {
            const min = field.getAttribute("minlength");
            if (min) return "Debe tener al menos " + min + " caracteres.";
            return "El valor es demasiado corto.";
        }
        if (validity.tooLong) {
            const max = field.getAttribute("maxlength");
            if (max) return "Debe tener como máximo " + max + " caracteres.";
            return "El valor es demasiado largo.";
        }
        if (validity.badInput) return "Introduce un valor válido para este campo.";
        if (validity.rangeUnderflow) {
            const min = field.getAttribute("min");
            return "El valor mínimo permitido es " + min + ".";
        }
        if (validity.rangeOverflow) {
            const max = field.getAttribute("max");
            return "El valor máximo permitido es " + max + ".";
        }

        return "Revisa este campo.";
    }

    function setFieldValidationState(field, isValid, errorMessage) {
        field.classList.remove(...fieldClassState.valid, ...fieldClassState.invalid);
        field.setAttribute("aria-invalid", isValid ? "false" : "true");

        const errorElement = ensureFieldErrorElement(field);

        if (isValid) {
            field.classList.add(...fieldClassState.valid);
            field.removeAttribute("title");
            errorElement.textContent = "";
            errorElement.classList.add("hidden");
            return;
        }

        field.classList.add(...fieldClassState.invalid);
        field.setCustomValidity(errorMessage);
        field.setAttribute("title", errorMessage);
        errorElement.textContent = errorMessage;
        errorElement.classList.remove("hidden");
    }

    function validateField(field) {
        field.setCustomValidity("");
        const isValid = field.checkValidity();
        const errorMessage = isValid ? "" : getErrorMessage(field);
        setFieldValidationState(field, isValid, errorMessage);
        return isValid;
    }

    function clearAllState() {
        setFormMessage("", "");
        fields.forEach(clearVisualState);
    }

    function clearFieldStatesOnly() {
        fields.forEach(clearVisualState);
    }

    fields.forEach((field) => {
        ensureFieldErrorElement(field);

        field.addEventListener("input", () => {
            validateField(field);
        });

        field.addEventListener("blur", () => {
            validateField(field);
        });
    });

    form.addEventListener("submit", (event) => {
        event.preventDefault();

        const invalidFields = fields.filter((field) => !validateField(field));

        if (invalidFields.length > 0) {
            invalidFields[0].focus();
            setFormMessage("error", "Faltan datos requeridos o hay campos inválidos. Revisa el formulario e inténtalo de nuevo.");
            return;
        }

        setFormMessage("success", "Solicitud enviada correctamente. Nuestro equipo te contactará en breve para continuar el proceso.");
        isSubmitReset = true;
        form.reset();
        clearFieldStatesOnly();
        isSubmitReset = false;
    });

    form.addEventListener("reset", () => {
        if (isSubmitReset) {
            clearFieldStatesOnly();
            return;
        }
        clearAllState();
    });
})();
