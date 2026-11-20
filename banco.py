import os

ARQUIVO_DB = "banco_dados.csv"
LIMITE_LINHAS = 50

def resetar_banco():
    try:
        if ARQUIVO_DB in os.listdir():
            os.remove(ARQUIVO_DB)
        print("Banco de dados resetado com sucesso.")
    except Exception as e:
        print("Erro ao resetar banco:", e)

def salvar_no_banco(data_hora, t, u, p, l, g):
    try:
        cabecalho = "Data_Hora,Temperatura_C,Umidade_UR,Pressao_hPa,Luminosidade_ADC,Qualidade_Ar_PPM\n"
        registro = "{},{},{},{},{},{}\n".format(data_hora, t, u, p, l, g)
        
        if ARQUIVO_DB not in os.listdir():
            with open(ARQUIVO_DB, "w") as f:
                f.write(cabecalho)
                f.write(registro)
            return

        with open(ARQUIVO_DB, "r") as f:
            linhas = f.readlines()
        
        dados = linhas[1:] if len(linhas) > 1 else []
        dados.append(registro)
        
        if len(dados) > LIMITE_LINHAS:
            dados = dados[-LIMITE_LINHAS:]
            
        with open(ARQUIVO_DB, "w") as f:
            f.write(cabecalho)
            for d in dados:
                f.write(d)
    except Exception as e:
        print("Erro ao persistir dados:", e)

def ler_historico_banco():
    if ARQUIVO_DB not in os.listdir():
        return []
        
    try:
        with open(ARQUIVO_DB, "r") as f:
            ultimas_linhas = []
            for i, linha in enumerate(f):
                if i == 0:
                    continue
                ultimas_linhas.append(linha.strip().split(","))
                if len(ultimas_linhas) > 8:
                    ultimas_linhas.pop(0)
            return ultimas_linhas
    except Exception as e:
        return []