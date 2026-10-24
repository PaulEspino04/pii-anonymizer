import os
import json
import hashlib
import pandas as pd
from faker import Faker

def titulo(texto):
    print("\n" + "=" * 70)
    print(texto)
    print("=" * 70)


def obtener_salt():
    """
    Obtiene el salt desde variables de entorno.
    PROHIBIDO: escribir el salt en el código (hardcoding).
    """
    salt = os.environ.get("SALT_SECRET")

    if not salt:
        raise EnvironmentError(
            "   La variable de entorno SALT_SECRET no está definida.\n"
            "   Configúrala antes de ejecutar el script:\n"
            "     Linux/macOS:  export SALT_SECRET='tu_salt_secreto'\n"
            "     Windows PS:   $env:SALT_SECRET='tu_salt_secreto'\n"
            "     Render:       Dashboard > Environment > Add Environment Variable"
        )

    if len(salt) < 8:
        raise ValueError(" SALT_SECRET demasiado corto (mínimo 8 caracteres recomendado).")

    print(f" SALT_SECRET cargado desde el entorno (longitud: {len(salt)} caracteres).")
    print("   -> El valor del salt NO se imprime por seguridad.\n")
    return salt

def generar_pii_sintetica(n_registros=50):
    """
    Genera n_registros con al menos 6 columnas que contienen datos privados.
    Todo en memoria (DataFrame de pandas).
    """
    fake = Faker("es_ES")
    Faker.seed(42)  

    registros = []
    for _ in range(n_registros):
        registros.append({
            "id": fake.uuid4(),                 
            "nombre": fake.name(),             
            "email": fake.email(),              
            "telefono": fake.phone_number(),     
            "edad": fake.random_int(min=18, max=85),      
            "salario": fake.random_int(min=15000, max=120000),  
            "ciudad": fake.city(),             
            "fecha_nacimiento": fake.date_of_birth(minimum_age=18, maximum_age=85).isoformat(),
        })

    df = pd.DataFrame(registros)
    print(f" Generados {len(df)} registros sintéticos en memoria.")
    print(f"   Columnas ({len(df.columns)}): {list(df.columns)}\n")
    print("   Muestra de datos originales (3 primeras filas):")
    print(df.head(3).to_string(index=False))
    print()

    assert len(df) >= 50, "Debe haber al menos 50 registros"
    assert len(df.columns) >= 6, "Debe haber al menos 6 columnas"
    print("Validación: >=50 registros y >=6 columnas cumplidos.\n")
    return df


def hash_con_salt(valor, salt):
    """SHA-256(salt + valor) -> hex. Unidireccional, resistente a rainbow tables."""
    return hashlib.sha256((salt + str(valor)).encode("utf-8")).hexdigest()


def anonimizar(df, salt):
    """
    - PII directa (nombre, email, telefono, id, fecha_nacimiento) -> hash SHA-256 con salt.
    - Numéricos (edad, salario) -> generalización por rangos (decenales / cuartiles).
    - Cuasi-identificador (ciudad) -> se conserva (útil para minería) o se puede
      generalizar; aquí se mantiene para no perder utilidad analítica.
    """
    df_anon = df.copy()

    columnas_hash = ["id", "nombre", "email", "telefono", "fecha_nacimiento"]
    for col in columnas_hash:
        df_anon[f"{col}_hash"] = df_anon[col].apply(lambda v: hash_con_salt(v, salt))

    bins_edad = [18, 30, 40, 50, 60, 70, 80, 90]
    labels_edad = ["18-29", "30-39", "40-49", "50-59", "60-69", "70-79", "80-89"]
    df_anon["edad_rango"] = pd.cut(
        df_anon["edad"], bins=bins_edad, labels=labels_edad, right=False
    )

    df_anon["salario_cuartil"] = pd.qcut(
        df_anon["salario"], q=4,
        labels=["Q1 (bajo)", "Q2 (medio-bajo)", "Q3 (medio-alto)", "Q4 (alto)"]
    )

    columnas_finales = [
        "id_hash", "nombre_hash", "email_hash", "telefono_hash",
        "fecha_nacimiento_hash",
        "edad_rango", "salario_cuartil",
        "ciudad",  # cuasi-identificador que se conserva para minería
    ]
    df_anon = df_anon[columnas_finales].copy()

    print(" Anonimización aplicada:")
    print("   - SHA-256 + salt -> id, nombre, email, telefono, fecha_nacimiento")
    print("   - Generalización -> edad (rangos decenales), salario (cuartiles)")
    print("   - Ciudad conservada como cuasi-identificador para utilidad analítica\n")
    print("   Muestra del dataset anonimizado (3 primeras filas):")
    print(df_anon.head(3).to_string(index=False))
    print()
    return df_anon

def verificar_utilidad(df_original, df_anon):
    """
    Demuestra que el dataset procesado sigue siendo útil para minería
    (agrupaciones, distribuciones) sin exponer PII.
    """
    print(" Verificación de utilidad para minería de datos:")
    print(f"   - Registros conservados: {len(df_anon)} / {len(df_original)}")

    print("\n   Distribución por edad_rango:")
    print(df_anon["edad_rango"].value_counts().sort_index().to_string())

    print("\n   Distribución por salario_cuartil:")
    print(df_anon["salario_cuartil"].value_counts().sort_index().to_string())

    print("\n Verificación de no-exposición de PII:")
    pii_original = ["nombre", "email", "telefono"]
    fuga = any(col in df_anon.columns for col in pii_original)
    assert not fuga, " Se filtró PII en texto plano"
    print("    Ninguna columna original de PII permanece en el dataset limpio.\n")


def persistir(df_anon, subir_s3=False):
    """
    Guarda el dataset limpio en CSV y JSON.
    Si subir_s3=True y hay credenciales en el entorno, sube a S3 (simulado).
    """
    csv_path = "dataset_anonimizado.csv"
    json_path = "dataset_anonimizado.json"

    df_anon.to_csv(csv_path, index=False)
    df_anon.to_json(json_path, orient="records", indent=2, force_ascii=False)

    print(f" Dataset limpio guardado en disco:")
    print(f"   - {csv_path}")
    print(f"   - {json_path}\n")

    if subir_s3:
        try:
            import boto3
            bucket = os.environ.get("S3_BUCKET")
            if not bucket:
                raise EnvironmentError("S3_BUCKET no definido en el entorno")
            s3 = boto3.client("s3")
            s3.upload_file(csv_path, bucket, csv_path)
            s3.upload_file(json_path, bucket, json_path)
            print(f" Subido a S3 bucket '{bucket}': {csv_path}, {json_path}\n")
        except ImportError:
            print(" boto3 no instalado. Se omite la subida real a S3.")
            print("   Simulación: los archivos están listos para subir manualmente.\n")
        except Exception as e:
            print(f" No se pudo subir a S3: {e}\n")
    else:
        print(" Persistencia local completada (subida a nube simulada).")
        print("   Para subir realmente a S3: pip install boto3 y exportar S3_BUCKET.\n")


def main():
    titulo("PASO 3: Gestión de secretos (variable de entorno)")
    salt = obtener_salt()

    titulo("PASO 1: Generación de PII sintética en memoria")
    df_original = generar_pii_sintetica(50)

    titulo("PASO 2: Anonimización (hashing con salt + generalización)")
    df_anon = anonimizar(df_original, salt)

    titulo("Validación de utilidad para minería de datos")
    verificar_utilidad(df_original, df_anon)

    titulo("PASO 4: Persistencia del dataset limpio")
    persistir(df_anon, subir_s3=False)

    titulo("PROCESO COMPLETADO")


if __name__ == "__main__":
    main()