#!/usr/bin/env python
# coding: utf-8

# In[3]:


def calcular_total_dias(data_inicio, data_termino):
    try:
        dt_inicio = datetime.strptime(data_inicio, "%Y-%m-%d")
        dt_termino = datetime.strptime(data_termino, "%Y-%m-%d")
        dias = (dt_termino - dt_inicio).days

        if dias < 0:
            gr.Warning("A data de término não pode ser anterior à data de início.")
            return [gr.update() for _ in args]
        return f"{dias} dias"
    except:
        return [gr.update() for _ in args]

# === Função principal ===
def processar_formulario(*args):
    nomes_completos = [
    "tipo_estagio", "razao_social", "cnpj", "nome_fantasia", "endereco", "bairro",
    "cep", "complemento", "cidade", "uf", "email", "telefone",
    "representante", "cpf_repr", "nome_estudante", "nascimento", "cpf_estudante", "rg",
    "endereco_estudante", "bairro_estudante", "cep_estudante", "complemento_estudante",
    "cidade_estudante", "uf_estudante",
    "email_estudante", "telefone_estudante", "curso_estudante",
    "ano_periodo", "matricula", "orientador",
    "data_inicio", "data_termino", "total_dias",
    "horas_diarias", "horas_semana_estagio", "total_horas_estagio",
    "seguradora", "apolice",
    "modalidade_estagio", "remunerado", "valor_bolsa", "valor_extenso",
    "auxilio_transporte", "especificacao_auxilio",
    "contraprestacao", "especificacao_contraprestacao",
    "horas_diarias_plano", "horas_semanais_plano", "total_horas_plano",
    "horario_atividades",
    "nome_supervisor", "formacao_supervisor", "registro_conselho"
    ]

with gr.Blocks(theme="default") as demo:    

    gr.Markdown("<h2 style='text-align: center;'>TERMO DE COMPROMISSO DE ESTÁGIO</h2>")
    
    gr.Markdown("(*) Preenchimento obrigatório")

    tipo_estagio = gr.Radio(
        choices=["CURRICULAR OBRIGATÓRIO", "NÃO OBRIGATÓRIO"],
        label="Tipo de Estágio*",
        value=None,
        elem_id="campo_tipo_estagio"
    )
    
    gr.Markdown("**Instrumento Jurídico de Termo de Compromisso de Estágio, sem vínculo empregatício, de que trata o art. 7º, inciso I da lei nº 11.788/2008.**")
    
    gr.Markdown("Este termo tem de um lado,")
    
    gr.Markdown("### DADOS DO(A) CONCEDENTE")

    with gr.Row():
        razao_social = gr.Text(label="Razão Social*")
        cnpj = gr.Text(label="CNPJ (00.000.000/0000-00)*", placeholder="Ex: 12.345.678/0001-99")
    
    nome_fantasia = gr.Text(label="Nome Fantasia*")
    
    # Botão de submissão
    botao = gr.Button("Registrar Termo")
    botao.click(
        fn=processar_formulario, 
        inputs=[
            tipo_estagio
             , razao_social
            , cnpj
            , nome_fantasia
            #, endereco, bairro, cep, complemento, cidade, uf, 
#             email, telefone, representante, cpf_repr, nome_estudante, nascimento, cpf_estudante, rg, 
#             endereco_estudante, bairro_estudante, cep_estudante, complemento_estudante, cidade_estudante, uf_estudante,
#             email_estudante, telefone_estudante, curso_estudante, ano_periodo, matricula,
#             orientador, data_inicio, data_termino, total_dias, horas_diarias, horas_semana_estagio, total_horas_estagio,
#             seguradora, apolice, modalidade_estagio, remunerado, valor_bolsa, valor_extenso, auxilio_transporte,
#             especificacao_auxilio, contraprestacao, especificacao_contraprestacao, horas_diarias_plano, horas_semanais_plano,
#             total_horas_plano, horario_atividades,
#             *atividades,
#             nome_supervisor, formacao_supervisor, registro_conselho
        ],
        outputs=[
            tipo_estagio
             , razao_social
            , cnpj
            , nome_fantasia
            #, endereco, bairro, cep, complemento, cidade, uf,
#             email, telefone, representante, cpf_repr, nome_estudante, nascimento, cpf_estudante, rg, 
#             endereco_estudante, bairro_estudante, cep_estudante, complemento_estudante, cidade_estudante, uf_estudante,
#             email_estudante, telefone_estudante, curso_estudante, ano_periodo, matricula,
#             orientador, data_inicio, data_termino, total_dias, horas_diarias, horas_semana_estagio, total_horas_estagio,
#             seguradora, apolice, modalidade_estagio, remunerado, valor_bolsa, valor_extenso, auxilio_transporte,
#             especificacao_auxilio, contraprestacao, especificacao_contraprestacao, horas_diarias_plano, horas_semanais_plano,
#             total_horas_plano, horario_atividades,
#             *atividades,
#             nome_supervisor, formacao_supervisor, registro_conselho
        ]
    )

import os

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 7860))
    demo.queue().launch(server_name="0.0.0.0", server_port=port)


# In[ ]:




