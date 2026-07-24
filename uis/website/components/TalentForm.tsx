"use client";

import { FormEvent, useMemo, useState } from "react";
import { TalentFormData, TalentFormErrors, validateTalentForm } from "@/lib/validation";

const initialData: TalentFormData = {
  nombreCompleto: "",
  email: "",
  telefono: "",
  pais: "",
  aniosExperiencia: "",
  sector: "",
  nivelIngles: "",
  disponibilidad: "",
  linkedin: "",
  comentarios: "",
  aceptaPolitica: false,
};

export function TalentForm() {
  const [data, setData] = useState<TalentFormData>(initialData);
  const [errors, setErrors] = useState<TalentFormErrors>({});
  const [isSubmitted, setIsSubmitted] = useState(false);

  const remaining = useMemo(() => 500 - data.comentarios.length, [data.comentarios.length]);

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setIsSubmitted(false);

    const validationErrors = validateTalentForm(data);
    setErrors(validationErrors);

    if (Object.keys(validationErrors).length > 0) {
      return;
    }

    setIsSubmitted(true);
    setData(initialData);
    setErrors({});
  }

  return (
    <form className="form" onSubmit={handleSubmit} noValidate>
      <div className="field">
        <label htmlFor="nombreCompleto">Nombre completo *</label>
        <input
          id="nombreCompleto"
          value={data.nombreCompleto}
          onChange={(event) =>
            setData((prev) => ({ ...prev, nombreCompleto: event.target.value }))
          }
        />
        {errors.nombreCompleto && <p className="error">{errors.nombreCompleto}</p>}
      </div>

      <div className="grid-2">
        <div className="field">
          <label htmlFor="email">Email *</label>
          <input
            id="email"
            type="email"
            value={data.email}
            onChange={(event) => setData((prev) => ({ ...prev, email: event.target.value }))}
          />
          {errors.email && <p className="error">{errors.email}</p>}
        </div>

        <div className="field">
          <label htmlFor="telefono">Telefono *</label>
          <input
            id="telefono"
            type="tel"
            placeholder="+34 612 345 678"
            value={data.telefono}
            onChange={(event) => setData((prev) => ({ ...prev, telefono: event.target.value }))}
          />
          {errors.telefono && <p className="error">{errors.telefono}</p>}
        </div>
      </div>

      <div className="grid-2">
        <div className="field">
          <label htmlFor="pais">Pais de residencia *</label>
          <select
            id="pais"
            value={data.pais}
            onChange={(event) => setData((prev) => ({ ...prev, pais: event.target.value }))}
          >
            <option value="">Selecciona una opcion</option>
            <option value="Espana">Espana</option>
            <option value="Estados Unidos">Estados Unidos</option>
            <option value="Otro">Otro</option>
          </select>
          {errors.pais && <p className="error">{errors.pais}</p>}
        </div>

        <div className="field">
          <label htmlFor="aniosExperiencia">Anos de experiencia *</label>
          <input
            id="aniosExperiencia"
            type="number"
            min={0}
            max={50}
            value={data.aniosExperiencia}
            onChange={(event) =>
              setData((prev) => ({ ...prev, aniosExperiencia: event.target.value }))
            }
          />
          {errors.aniosExperiencia && <p className="error">{errors.aniosExperiencia}</p>}
        </div>
      </div>

      <div className="grid-2">
        <div className="field">
          <label htmlFor="sector">Sector de interes *</label>
          <select
            id="sector"
            value={data.sector}
            onChange={(event) => setData((prev) => ({ ...prev, sector: event.target.value }))}
          >
            <option value="">Selecciona una opcion</option>
            <option value="Tecnologia">Tecnologia</option>
            <option value="Retail">Retail</option>
            <option value="Servicios Financieros">Servicios Financieros</option>
            <option value="Consultoria">Consultoria</option>
            <option value="Otro">Otro</option>
          </select>
          {errors.sector && <p className="error">{errors.sector}</p>}
        </div>

        <div className="field">
          <label htmlFor="nivelIngles">Nivel de ingles *</label>
          <select
            id="nivelIngles"
            value={data.nivelIngles}
            onChange={(event) =>
              setData((prev) => ({ ...prev, nivelIngles: event.target.value }))
            }
          >
            <option value="">Selecciona una opcion</option>
            <option value="Basico">Basico</option>
            <option value="Intermedio">Intermedio</option>
            <option value="Avanzado">Avanzado</option>
            <option value="Nativo">Nativo</option>
          </select>
          {errors.nivelIngles && <p className="error">{errors.nivelIngles}</p>}
        </div>
      </div>

      <fieldset className="field availability-group">
        <legend>Disponibilidad *</legend>
        <label>
          <input
            type="radio"
            name="disponibilidad"
            value="Inmediata"
            checked={data.disponibilidad === "Inmediata"}
            onChange={(event) =>
              setData((prev) => ({ ...prev, disponibilidad: event.target.value }))
            }
          />
          Inmediata
        </label>
        <label>
          <input
            type="radio"
            name="disponibilidad"
            value="1 mes"
            checked={data.disponibilidad === "1 mes"}
            onChange={(event) =>
              setData((prev) => ({ ...prev, disponibilidad: event.target.value }))
            }
          />
          1 mes
        </label>
        <label>
          <input
            type="radio"
            name="disponibilidad"
            value="2-3 meses"
            checked={data.disponibilidad === "2-3 meses"}
            onChange={(event) =>
              setData((prev) => ({ ...prev, disponibilidad: event.target.value }))
            }
          />
          2-3 meses
        </label>
        <label>
          <input
            type="radio"
            name="disponibilidad"
            value="Solo explorando"
            checked={data.disponibilidad === "Solo explorando"}
            onChange={(event) =>
              setData((prev) => ({ ...prev, disponibilidad: event.target.value }))
            }
          />
          Solo explorando
        </label>
        {errors.disponibilidad && <p className="error">{errors.disponibilidad}</p>}
      </fieldset>

      <div className="field">
        <label htmlFor="linkedin">LinkedIn (URL del perfil)</label>
        <input
          id="linkedin"
          type="url"
          placeholder="https://www.linkedin.com/in/tu-perfil"
          value={data.linkedin}
          onChange={(event) => setData((prev) => ({ ...prev, linkedin: event.target.value }))}
        />
        {errors.linkedin && <p className="error">{errors.linkedin}</p>}
      </div>

      <div className="field">
        <label htmlFor="comentarios">Comentarios adicionales</label>
        <textarea
          id="comentarios"
          maxLength={500}
          value={data.comentarios}
          onChange={(event) => setData((prev) => ({ ...prev, comentarios: event.target.value }))}
        />
        <p className="hint">Maximo 500 caracteres. Quedan {remaining}.</p>
        {errors.comentarios && <p className="error">{errors.comentarios}</p>}
      </div>

      <label className="checkbox-field" htmlFor="aceptaPolitica">
        <input
          id="aceptaPolitica"
          type="checkbox"
          checked={data.aceptaPolitica}
          onChange={(event) =>
            setData((prev) => ({ ...prev, aceptaPolitica: event.target.checked }))
          }
        />
        Acepto politica de datos y tratamiento de informacion.
      </label>
      {errors.aceptaPolitica && <p className="error">{errors.aceptaPolitica}</p>}

      <button className="button-primary" type="submit">
        Enviar registro
      </button>

      {isSubmitted && (
        <div className="success-box" role="status" aria-live="polite">
          <p>
            <strong>Gracias por tu interes en Nexova!</strong>
          </p>
          <p>
            Hemos recibido tu informacion. Nuestro equipo de seleccion la
            revisara y te contactaremos en caso de que tu perfil encaje con
            alguna de nuestras oportunidades actuales o futuras.
          </p>
          <p>
            Mientras tanto, siguenos en LinkedIn para estar al dia de nuestras
            vacantes y contenido sobre desarrollo profesional.
          </p>
        </div>
      )}
    </form>
  );
}
