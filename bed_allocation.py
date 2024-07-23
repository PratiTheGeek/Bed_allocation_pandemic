from flask import Flask, render_template, request, redirect, url_for,send_file
import psycopg2
import pandas as pd
import csv
import io

app = Flask(__name__)

#conection with database
connection = psycopg2.connect(
    database="postgres",
    user="postgres",
    password="1234",
    host="localhost",
    port="5432"
)

cursor1 = connection.cursor()
hospital_data_query = "SELECT * FROM hospital_dataset"
cursor1.execute(hospital_data_query)
hospital_data = cursor1.fetchall()

df_hosp = pd.DataFrame(hospital_data, columns=[desc[0] for desc in cursor1.description])
available_hospitals = []

def get_patrow_onlywithid(patientid):
    conn= connection.cursor()
    conn.execute('select * from patient_data where patientid=patientid')
    row = conn.fetchone()
    return row


def get_input(email,password,patient_id) -> tuple:
 #thsi function will return row of particular patient 
    try:
        cursor = connection.cursor()
        cursor.execute("SELECT * FROM patient_data WHERE email = %s AND password = %s AND patientid = %s", (email, password, patient_id))

        
        result=cursor.fetchone()
        cursor.close()


    except (Exception, psycopg2.Error) as error:
        ##print("Error while executing SQL query:", error)
        return []
    
    return result


def get_allocationcrt(patient_row):
    patient_age = patient_row[2]
    patient_temperature = patient_row[5]
    patient_spo2 = patient_row[6]
    patient_finding = patient_row[4]

    if patient_temperature < 38 and patient_spo2 >= 95:
        Advice = "Voluntary quarantine and proper medication"
        allocation_criteria = []
    else:

        if patient_finding == 'COVID-19':
            if patient_age > 60:
                allocation_criteria = ['icu_beds', 'special_wards', 'semi_special_wards', 'general_ward_beds']
                Advice = "Direct ICU or Special/Semi-Special/General ward"
            elif 35 <= patient_age <= 60:
                if patient_temperature == 'Severe':
                    allocation_criteria = ['special_wards', 'semi_special_wards']
                    Advice = "Special/Semi-Special ward"
                elif patient_temperature == 'Moderate':
                    if patient_spo2 == 'Severe' or patient_spo2 == 'Moderate':
                        allocation_criteria = ['special_wards', 'semi_special_wards']
                        Advice = "Special/Semi-Special ward"
                    else:
                        allocation_criteria = ['general_ward_beds']
                        Advice = "General ward"
            else:  # Age < 35
                if patient_temperature == 'Severe' and (patient_spo2 == 'Severe' or patient_spo2 == 'Moderate'):
                    allocation_criteria = ['special_wards', 'semi_special_wards']
                    Advice = "Special/Semi-Special ward"
                elif patient_temperature == 'Moderate' and (patient_spo2 == 'Severe' or patient_spo2 == 'Moderate'):
                    allocation_criteria = ['semi_special_wards', 'general_ward_beds']
                    Advice = "Semi-Special/General ward"

        
        Advice="Semi-Special/General ward"
        allocation_criteria=['semi_special_wards', 'general_ward_beds']

    return [Advice,allocation_criteria]
    
def get_availabehosp(patient_row, allocation_criteria, df_hosp):
    matching_hospitals = df_hosp.copy()
    matching_hospitals['distance'] = abs(matching_hospitals['pincode'] - patient_row[0])
    matching_hospitals = matching_hospitals.sort_values(by=['distance'])

    available_hospitals = []
    option_counter = 0

    for _, hospital in matching_hospitals.iterrows():
        is_available = True
        
        for criteria in allocation_criteria:
            if hospital[criteria] == 0:
                is_available = False
                break
        if is_available:
            for criteria in allocation_criteria:
                option_counter += 1
                available_hospitals.append({
                    'option': option_counter,
                    'hospital_id': hospital['hospital_id'],
                    'hospital_name': hospital['hospital_name'],
                    'criteria': criteria
                })
            

    return available_hospitals
    
def update_hos(id, cr, df_hosp):
    """Updates the capacity of a hospital in the database based on its ID and capacity column.

    Args:
        id (int): The hospital ID to update.
        cr (str): The name of the column representing hospital capacity (assuming numerical).

    Returns:
        None
    """

    try:
       
        with connection.cursor() as cursor:  # Use context manager for proper resource management
            # Update capacity directly in the DataFrame
            for index, hospital in df_hosp.iterrows():
                if hospital['hospital_id'] == id:
                    hospital[cr] -= 1
                    break  # Exit loop after finding the matching hospital

            # Update the specific hospital record in the database using SQL
            if hospital['hospital_id'] == id:  # Check if hospital found before SQL update
                sql = f"UPDATE hospital_dataset SET {cr} = {hospital[cr]} WHERE hospital_id = {id}"
                cursor.execute(sql)
                connection.commit()
                return f"The bed has been allocated successfully"
            else:
                return f"Hospital ID {id} not found in the DataFrame."

    except (Exception, psycopg2.Error) as error:  # Catch broader exceptions for better handling
        return print("Error while updating hospital capacity:", error)

    finally:
        if connection:  # Close the connection if it was created
            connection.close()
@app.route('/index')
def index():
    return render_template("index.html")

@app.route("/login", methods=["GET", "POST"])
def login():
  #this function will render login page and get data from user from website and check if it is proper data or not  
    if request.method == "POST":
        email = request.form["email"]
        password = request.form["password"]
        patient_id = request.form["patientId"]
        
        user = get_input(email, password, patient_id)
        
        if user:
            return redirect(url_for('after_login',patientid = patient_id))
        else:
            return redirect(url_for('not_login'))
        
        
    return render_template('login.html')

@app.route("/not_login")
def not_login():
    return "user not found"

@app.route("/after_login/<int:patientid>")
def after_login(patientid):
    return render_template('afterlogin.html',patientid=patientid)

@app.route("/after_login/submit/<int:patientid>", methods=['GET', 'POST'])
def after_login_submit(patientid):
    app.logger.info(f"Request method: {request.method}")
    if request.method == "POST":
        addDet = request.form["addDetails"]
        
        if addDet == 'yes':
            return "not working right now"
        elif addDet == "no":
             return redirect(url_for('bedallocation',patientid=patientid))
            # render_template("bedallocate.html",patientid=patientid)
        else:
            # Handle cases where addDet has an unexpected value
            return "Invalid option selected. Please choose yes or no."
            
    # Handle GET requests
    return redirect(url_for('after_login', patientid=patientid))

@app.route('/bedallocation/<int:patientid>',methods=['GET','POST'])
def bedallocation(patientid):
    
    if request.method == 'POST' and request.json and request.json.get('download_csv'):
        patient_row = get_patrow_onlywithid(patientid)
        allocation_criteria = get_allocationcrt(patient_row)
        available_hospitals = get_availabehosp(patient_row, allocation_criteria[1], df_hosp)

        df_available_hospitals = pd.DataFrame(available_hospitals)
        csv_content = df_available_hospitals.to_csv(index=False)
        temp_csv_path = f'temp_data_{patientid}.csv'
        with open(temp_csv_path, 'w') as file:
            file.write(csv_content)

        return send_file(temp_csv_path, as_attachment=True)

    else:
        patient_row = get_patrow_onlywithid(patientid)
        allocation_criteria = get_allocationcrt(patient_row)
        return render_template('bedallocate.html', patient_row=patient_row, Advice=allocation_criteria[1], patientid=patientid)
    
@app.route('/update/<int:patientid>', methods=['GET', 'POST'])
def update(patientid):
    patient_row = get_patrow_onlywithid(patientid)
    allocation_criteria = get_allocationcrt(patient_row)
    available_hospitals = get_availabehosp(patient_row, allocation_criteria[1], df_hosp)
    if request.method == 'POST':
        selected_option = int(request.form['hospital_option'])
        selected_hospital = available_hospitals[selected_option - 1]  # Adjust for 0-based index
        id = selected_hospital['hospital_id']
        cr = selected_hospital['criteria']
        # Process the selected hospital option here
        ans = update_hos(id,cr,df_hosp)
        # You can redirect or perform further actions based on the selected option
        # return redirect(url_for('selected_hospital', patientid=patientid,ans=ans))
        return render_template('final.html',ans=ans,patientid=patientid)
    else:
        # patient_row = get_patrow_onlywithid(patientid)
        # allocation_criteria = get_allocationcrt(patient_row)
        # available_hospitals = get_availabehosp(patient_row, allocation_criteria[1], df_hosp)
        return render_template('chooseopt.html', available_hospitals=available_hospitals, patientid=patientid)



if __name__ == "__main__":
    app.run(debug=True)