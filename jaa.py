# -----------start
@app.post("/scopewise_total_taken", response_model=List[dict])
def get_total_time(
    picked_date: Annotated[str, Form()],
    to_date: Annotated[str, Form()],
    db: Session = Depends(get_db)
):
    picked_date_obj = datetime.strptime(picked_date, "%Y-%m-%d").date()
    to_date_obj = datetime.strptime(to_date, "%Y-%m-%d").date()
    current_date = date.today()


    total_times = []


    if to_date_obj < current_date and picked_date_obj < current_date:
        total_times = crud.pastdate_userwise_report9(db, picked_date, to_date)


    elif to_date_obj == current_date and picked_date_obj == current_date:
        total_times = crud.calculate_end_time_for_user9(db, picked_date, to_date)


    elif picked_date_obj < current_date and to_date_obj == current_date:
        past_times = crud.pastdate_userwise_report9(db, picked_date, picked_date)
        current_times = crud.calculate_end_time_for_user9(db, str(to_date_obj), str(to_date_obj))
        total_times = crud.combine_scope_times(past_times, current_times)


    return total_times


# ----------------------end



from collections import defaultdict, OrderedDict
from datetime import datetime, timedelta


def format_timedelta_to_str(td: timedelta) -> str:
    """Formats a timedelta object into a string."""
    total_seconds = int(td.total_seconds())
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02}:{minutes:02}:{seconds:02}"




def calculate_end_time_for_user9(db: Session, picked_date: str, to_date: str) -> list:
    """Scope-wise aggregated time taken."""
    picked_datett = datetime.strptime(picked_date, "%Y-%m-%d")
    to_datett = datetime.strptime(to_date, "%Y-%m-%d")
    current_time = datetime.now()  # For ongoing activities


    def process_records_for_day(date, activity, records, start_field, end_field, user_field, scope_times):
        for record in records:
            start_time = getattr(record, start_field)
            end_time = getattr(record, end_field) or current_time  # Use current_time if ongoing


            # Ensure the record falls exactly on the specified date
            if start_time.date() != date:
                continue


            time_diff = end_time - start_time


            # Fetch TL record for work status and metadata
            service_id = getattr(record, 'Service_ID')
            tl_record = db.query(models.TL).filter(
                models.TL.Service_ID == service_id
            ).first()


            scope = tl_record.scope.scope if tl_record else "Unknown Scope"
            type_of_activity = tl_record.type_of_activity if tl_record else "Unknown"


            # Determine whether the time is chargeable or non-chargeable
            if scope not in scope_times:
                scope_times[scope] = {'Chargable_Time': timedelta(0), 'Non_Chargable_Time': timedelta(0)}


            if type_of_activity == "CHARGABLE":
                scope_times[scope]['Chargable_Time'] += time_diff
            elif type_of_activity == "Non-Charchable":
                scope_times[scope]['Non_Chargable_Time'] += time_diff


    # Main function logic
    aggregated_times = defaultdict(lambda: {'Chargable_Time': timedelta(0), 'Non_Chargable_Time': timedelta(0)})
    current_day = picked_datett


    while current_day <= to_datett:
        scope_times = defaultdict(lambda: {'Chargable_Time': timedelta(0), 'Non_Chargable_Time': timedelta(0)})


        # Process each activity type
        for activity, model, start_field, end_field in [
            ('in_progress', models.INPROGRESS, 'start_time', 'end_time'),
        ]:
            records = db.query(model).filter(
                getattr(model, start_field).between(
                    current_day.replace(hour=0, minute=0, second=0),
                    current_day.replace(hour=23, minute=59, second=59)
                )
            ).all()


            # Process records
            process_records_for_day(current_day.date(), activity, records, start_field, end_field, 'user_id', scope_times)


        # Aggregate daily times into the overall summary
        for scope, times in scope_times.items():
            aggregated_times[scope]['Chargable_Time'] += times['Chargable_Time']
            aggregated_times[scope]['Non_Chargable_Time'] += times['Non_Chargable_Time']


        current_day += timedelta(days=1)


    # Format the aggregated output
    formatted_output = []
    for idx, (scope, times) in enumerate(aggregated_times.items(), start=1):
        formatted_output.append({
            "date": current_day.strftime("%Y-%m-%d"),
            "Nature_of_Scope": scope,
            "Chargable_Time": format_timedelta_to_str(times['Chargable_Time']),
            "Non_Chargable_Time": format_timedelta_to_str(times['Non_Chargable_Time']),
            "total_time_take": format_timedelta_to_str(
                times['Chargable_Time'] + times['Non_Chargable_Time']
            ),
        })


    return formatted_output






# ------------------pastdate
def pastdate_userwise_report9(db: Session, picked_date: str, to_date: str) -> list:
    '''scopewisetimetaken'''
    picked_datett = datetime.strptime(picked_date, "%Y-%m-%d")
    to_datett = datetime.strptime(to_date, "%Y-%m-%d")


    daily_summaries = []


    current_day = picked_datett
    while current_day <= to_datett:
        user_times = defaultdict(lambda: defaultdict(dict))


        # Query total time taken for the current day and join with TL table
        records = db.query(models.TotalTimeTaken).join(
            models.TL, models.TotalTimeTaken.service_id == models.TL.Service_ID
        ).filter(
            models.TotalTimeTaken.date == current_day.date()
        ).all()


        # Process the records
        for record in records:
            # Fetch username from the User_table
            username = db.query(models.User_table.username).filter(
                models.User_table.user_id == record.user_id
            ).scalar() or "Unknown"


            service_id = record.service_id
           
            # Fetch additional fields from TL
            tl_record = db.query(models.TL).filter(models.TL.Service_ID == service_id).first()
   
            chargable_time = "00:00:00"
            Non_Chargable_Time = "00:00:00"
            entity = None


            if tl_record:
                entity = tl_record.name_of_entity  # Assuming this is directly from TL


                scope = db.query(models.scope).filter(models.scope.scope_id == tl_record.Scope).first()


                # Determine Chargable_Time based on type of activity
                if tl_record.type_of_activity == "CHARGABLE":
                    chargable_time = record.total_inprogress_time or "00:00:00"
                elif tl_record.type_of_activity == "Non-Charchable":
                    Non_Chargable_Time = record.total_inprogress_time or "00:00:00"
               
                # Fetch the scope name
                scope_name = scope.scope if scope else "Unknown"
            else:
                scope_name = "Unknown"


            # Function to convert time strings to seconds
            def time_to_seconds(time_str):
                if time_str == "00:00:00":
                    return 0
                hours, minutes, seconds = map(int, time_str.split(':'))
                return hours * 3600 + minutes * 60 + seconds


            # Function to convert seconds back to HH:MM:SS
            def seconds_to_time(seconds):
                hours = seconds // 3600
                minutes = (seconds % 3600) // 60
                seconds = seconds % 60
                return f"{hours:02}:{minutes:02}:{seconds:02}"


            # Aggregate time for the username and scope
            user_times[scope_name]['Chargable_Time'] = (
                seconds_to_time(time_to_seconds(user_times[scope_name].get('Chargable_Time', "00:00:00")) + time_to_seconds(chargable_time))
            )
            user_times[scope_name]['Non_Chargable_Time'] = (
                seconds_to_time(time_to_seconds(user_times[scope_name].get('Non_Chargable_Time', "00:00:00")) + time_to_seconds(Non_Chargable_Time))
            )


            # Calculate total time in seconds
            total_seconds = time_to_seconds(user_times[scope_name]['Chargable_Time']) + time_to_seconds(user_times[scope_name]['Non_Chargable_Time'])
            user_times[scope_name]['Total_Time'] = seconds_to_time(total_seconds)


        # Only add the summary if there was data for the day
        if user_times:
            for scope_name, times in user_times.items():
                daily_summaries.append({
                    "date": current_day.strftime("%Y-%m-%d"),
                    "Nature_of_Scope": scope_name,
                    "Chargable_Time": times['Chargable_Time'],
                    "Non_Chargable_Time": times['Non_Chargable_Time'],
                    "total_time_take": times['Total_Time']
                })


        current_day += timedelta(days=1)


    return daily_summaries










def combine_scope_times(past_times, current_times):
    """Combine past and current times for matching Nature of Scope."""
    combined_times = defaultdict(lambda: {'Chargable_Time': "00:00:00", 'Non_Chargable_Time': "00:00:00"})


    def time_to_seconds(time_str):
        hours, minutes, seconds = map(int, time_str.split(':'))
        return hours * 3600 + minutes * 60 + seconds


    def seconds_to_time(seconds):
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        seconds = seconds % 60
        return f"{hours:02}:{minutes:02}:{seconds:02}"


    # Combine times from past and current records
    for times in past_times + current_times:
        scope = times['Nature_of_Scope']
        combined_times[scope]['Chargable_Time'] = seconds_to_time(
            time_to_seconds(combined_times[scope]['Chargable_Time']) +
            time_to_seconds(times['Chargable_Time'])
        )
        combined_times[scope]['Non_Chargable_Time'] = seconds_to_time(
            time_to_seconds(combined_times[scope]['Non_Chargable_Time']) +
            time_to_seconds(times['Non_Chargable_Time'])
        )


    # Format the combined result into the desired structure
    combined_output = []
    for scope, times in combined_times.items():
        total_seconds = (
            time_to_seconds(times['Chargable_Time']) + time_to_seconds(times['Non_Chargable_Time'])
        )
        combined_output.append({
            "date": f"{past_times[0]['date']} ,{current_times[0]['date']}" if past_times and current_times else "",
            "Nature_of_Scope": scope,
            "Chargable_Time": times['Chargable_Time'],
            "Non_Chargable_Time": times['Non_Chargable_Time'],
            "total_time_take": seconds_to_time(total_seconds)
        })


    return combined_output




# --------------------------------scope_total_taken




________________________________


# -----------start
@app.post("/scopecumsubcope_total_taken", response_model=List[dict])
def get_total_time(
    picked_date: Annotated[str, Form()],
    to_date: Annotated[str, Form()],
    db: Session = Depends(get_db)
):
    # Convert strings to date objects
    picked_date_obj = datetime.strptime(picked_date, "%Y-%m-%d").date()
    to_date_obj = datetime.strptime(to_date, "%Y-%m-%d").date()
    current_date = date.today()  # Get the current date without time


    total_times = []


    # Check if both picked_date and to_date are less than current date
    if to_date_obj < current_date and picked_date_obj < current_date:
        total_times = crud.pastdate_userwise_report10(db, picked_date, to_date)


    # Check if both picked_date and to_date are equal to current date
    elif to_date_obj == current_date and picked_date_obj == current_date:
        total_times = crud.calculate_end_time_for_user10(db, picked_date, to_date)


    elif picked_date_obj < current_date and to_date_obj == current_date:
        past_times = crud.pastdate_userwise_report10(db, picked_date, picked_date)
        current_times = crud.calculate_end_time_for_user10(db, str(to_date_obj), str(to_date_obj))
        total_times = crud.combine_scopesub_times(past_times, current_times)


    return total_times
# ----------------------end



# --------------------------------scopecumsubcope_total_taken
#past functin-----------------------------
def pastdate_userwise_report10(db: Session, picked_date: str, to_date: str) -> dict:
    '''scope cum subscope timetaken'''
    picked_datett = datetime.strptime(picked_date, "%Y-%m-%d")
    to_datett = datetime.strptime(to_date, "%Y-%m-%d")


    daily_summaries = []  # Changed to a list to hold each day's summaries
    current_day = picked_datett


    while current_day <= to_datett:
        user_times = defaultdict(lambda: defaultdict(lambda: defaultdict(lambda: defaultdict(dict))))


        # Query total time taken for the current day and join with TL table
        records = db.query(models.TotalTimeTaken).join(
            models.TL, models.TotalTimeTaken.service_id == models.TL.Service_ID
        ).filter(
            models.TotalTimeTaken.date == current_day.date()
        ).all()


        # Process the records
        for record in records:
            # Fetch username from the User_table
            username = db.query(models.User_table.username).filter(
                models.User_table.user_id == record.user_id
            ).scalar() or "Unknown"


            service_id = record.service_id
           
            # Fetch additional fields from TL
            tl_record = db.query(models.TL).filter(models.TL.Service_ID == service_id).first()
   
            chargable_time = "00:00:00"
            non_chargable_time = "00:00:00"
            entity = None


            if tl_record:
                entity = tl_record.name_of_entity  # Assuming this is directly from TL


                scope = db.query(models.scope).filter(models.scope.scope_id == tl_record.Scope).first()
                subscope = db.query(models.sub_scope).filter(models.sub_scope.sub_scope_id == tl_record.From).first()


                # Determine Chargable_Time based on type of activity
                if tl_record.type_of_activity == "CHARGABLE":
                    chargable_time = record.total_inprogress_time or "00:00:00"
                elif tl_record.type_of_activity == "Non-Charchable":
                    non_chargable_time = record.total_inprogress_time or "00:00:00"
               
                # Fetch the scope name
                scope_name = scope.scope if scope else "Unknown"
                subscope_name = subscope.sub_scope if subscope else "unknown"  
            else:
                scope_name = "Unknown"
                subscope_name = "unknown"


            # Function to convert time strings to seconds
            def time_to_seconds(time_str):
                if time_str == "00:00:00":
                    return 0
                hours, minutes, seconds = map(int, time_str.split(':'))
                return hours * 3600 + minutes * 60 + seconds


            # Function to convert seconds back to HH:MM:SS
            def seconds_to_time(seconds):
                hours = seconds // 3600
                minutes = (seconds % 3600) // 60
                seconds = seconds % 60
                return f"{hours:02}:{minutes:02}:{seconds:02}"


            # Aggregate times
            user_times[username][scope_name][subscope_name][service_id] = {
                'in_progress': record.total_inprogress_time or "00:00:00",
                'entity': entity,
                'scope': scope_name,
                'subscope': subscope_name,
                'Chargable_Time': chargable_time,
                'Non_Chargable_Time': non_chargable_time,
                'Total_Time': "00:00:00"  # Initialize Total_Time to zero
            }


        # Aggregate the totals for each user, scope, and subscope
        for username, scopes in user_times.items():
            for scope_name, subscopes in scopes.items():
                for subscope_name, services in subscopes.items():
                    total_chargable_seconds = 0
                    total_non_chargable_seconds = 0


                    for service_id, times in services.items():
                        total_chargable_seconds += time_to_seconds(times['Chargable_Time'])
                        total_non_chargable_seconds += time_to_seconds(times['Non_Chargable_Time'])
                        # Update the in_progress and entity if needed
                        user_times[username][scope_name][subscope_name][service_id]['Total_Time'] = times['Total_Time']


                    # Set aggregated Chargable and Non-Chargable Time
                    aggregated_chargable_time = seconds_to_time(total_chargable_seconds)
                    aggregated_non_chargable_time = seconds_to_time(total_non_chargable_seconds)


                    # Update the first entry for the subscope with aggregated times
                    user_times[username][scope_name][subscope_name]['Chargable_Time'] = aggregated_chargable_time
                    user_times[username][scope_name][subscope_name]['Non_Chargable_Time'] = aggregated_non_chargable_time
                    user_times[username][scope_name][subscope_name]['Total_Time'] = seconds_to_time(total_chargable_seconds + total_non_chargable_seconds)


        # Only add the summary if there was data for the day
        if user_times:
            for username, scopes in user_times.items():
                for scope_name, subscopes in scopes.items():
                    for subscope_name, services in subscopes.items():
                        formatted_day_summary = {
                            "date": current_day.strftime("%Y-%m-%d"),  # Date as a key-value pair
                            "nature_of_scope": scope_name,
                            "SubScope": subscope_name,
                            'Chargable_Time': user_times[username][scope_name][subscope_name]['Chargable_Time'],
                            'Non_Chargable_Time': user_times[username][scope_name][subscope_name]['Non_Chargable_Time'],
                            'Total_Time_Taken': user_times[username][scope_name][subscope_name]['Total_Time'],  # Fetch Total_Time from user_times
                        }


                        daily_summaries.append(formatted_day_summary)  # Add each entry to the list


        current_day += timedelta(days=1)


    return daily_summaries
#current funtion--------------------------------------
def calculate_end_time_for_user10(db: Session, picked_date: str, to_date: str) -> dict:
    '''scope cum subscope time takien'''
    picked_datett = datetime.strptime(picked_date, "%Y-%m-%d")
    to_datett = datetime.strptime(to_date, "%Y-%m-%d")
    current_time = datetime.now()  # For ongoing activities


    def process_records_for_day(date, activity, records, start_field, end_field, user_field, user_times):
        has_activity_for_day = False


        for record in records:
            start_time = getattr(record, start_field)
            end_time = getattr(record, end_field) or current_time


            # Ensure the record falls exactly on the specified date
            if start_time.date() != date:
                continue


            time_diff = end_time - start_time
            has_activity_for_day = True


            # Fetch user from User_table
            user = db.query(models.User_table).filter(
                models.User_table.user_id == getattr(record, user_field)
            ).first()
           
            username = f"{user.firstname} {user.lastname}" if user else "Unknown"


            service_id = getattr(record, 'Service_ID')


            # Fetch TL record for work status and metadata
            tl_record = db.query(models.TL).filter(
                models.TL.Service_ID == service_id
            ).first()


            scope = db.query(models.scope).filter(models.scope.scope_id == tl_record.Scope).first()
            subscope = db.query(models.sub_scope).filter(models.sub_scope.sub_scope_id == tl_record.From).first()
               
            # Get the entity name and type_of_activity
            entity_name = tl_record.name_of_entity if tl_record else "Unknown Entity"
            type_of_activity = tl_record.type_of_activity if tl_record else "Unknown"
            scope = tl_record.scope.scope if tl_record else "Unknown"
            subscope = subscope.sub_scope if tl_record else "Unknown"


            # Determine chargable and non-chargable times
            if type_of_activity == "CHARGABLE":
                chargable_time = time_diff
                non_chargable_time = timedelta(0)
            elif type_of_activity == "Non-Charchable":
                chargable_time = timedelta(0)
                non_chargable_time = time_diff
            else:
                chargable_time = non_chargable_time = timedelta(0)


            # Initialize user_times if not present
            if (username, entity_name) not in user_times:
                user_times[(username, entity_name)][service_id] = {
                    'Chargable_Time': timedelta(0),
                    'Non_Chargable_Time': timedelta(0),
                    'nature_of_scope': scope,  # Store the nature of work here
                    'subscope': subscope,
                }


            user_times[(username, entity_name)][service_id]['Chargable_Time'] += chargable_time
            user_times[(username, entity_name)][service_id]['Non_Chargable_Time'] += non_chargable_time


        return has_activity_for_day




    daily_summaries = []
    current_day = picked_datett


    while current_day <= to_datett:
        user_times = defaultdict(lambda: defaultdict(lambda: defaultdict(timedelta)))


        # Track if any activities were processed for the current day
        day_has_data = False


        # Process each activity type
        for activity, model, start_field, end_field in [


            ('in_progress', models.INPROGRESS, 'start_time', 'end_time'),
        ]:
            records = db.query(model).filter(
                getattr(model, start_field).between(
                    current_day.replace(hour=0, minute=0, second=0),
                    current_day.replace(hour=23, minute=59, second=59)
                )
            ).all()


            # Process records and check if there was any valid data
            if process_records_for_day(current_day.date(), activity, records, start_field, end_field, 'user_id', user_times):
                day_has_data = True


        # Only add the summary if there was data for the day
        if day_has_data:
            for (username, entity_name) in user_times:
                for service_id in user_times[(username, entity_name)]:
                    summary = {
                        'date': current_day.strftime("%Y-%m-%d"),
                        'service_id': service_id,
                        'nature_of_scope': user_times[(username, entity_name)][service_id]['nature_of_scope'],
                        'SubScope': user_times[(username, entity_name)][service_id]['subscope'],
                        'Chargable_Time': format_timedelta_to_str(user_times[(username, entity_name)][service_id]['Chargable_Time']),
                        'Non_Chargable_Time': format_timedelta_to_str(user_times[(username, entity_name)][service_id]['Non_Chargable_Time']),
                        'Total_Time_Taken': format_timedelta_to_str(
                            user_times[(username, entity_name)][service_id]['Chargable_Time'] +
                            user_times[(username, entity_name)][service_id]['Non_Chargable_Time']
                        )
                    }
                    daily_summaries.append(summary)


        current_day += timedelta(days=1)


    return daily_summaries








from collections import defaultdict
from datetime import timedelta


def combine_scopesub_times(past_times, current_times):
    """Combine past and current times for matching Nature of Scope."""
    combined_times = defaultdict(lambda: defaultdict(lambda: {'Chargable_Time': "00:00:00", 'Non_Chargable_Time': "00:00:00"}))


    def time_to_seconds(time_str):
        """Convert HH:MM:SS string to seconds."""
        hours, minutes, seconds = map(int, time_str.split(':'))
        return hours * 3600 + minutes * 60 + seconds


    def seconds_to_time(seconds):
        """Convert seconds to HH:MM:SS string."""
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        seconds = seconds % 60
        return f"{hours:02}:{minutes:02}:{seconds:02}"


    # Combine times from past and current records
    for times in past_times + current_times:
        scope = times['nature_of_scope']
        subcope = times['SubScope']  # Corrected the spelling here
        combined_times[scope][subcope]['Chargable_Time'] = seconds_to_time(
            time_to_seconds(combined_times[scope][subcope]['Chargable_Time']) +
            time_to_seconds(times['Chargable_Time'])
        )
        combined_times[scope][subcope]['Non_Chargable_Time'] = seconds_to_time(
            time_to_seconds(combined_times[scope][subcope]['Non_Chargable_Time']) +
            time_to_seconds(times['Non_Chargable_Time'])
        )


    # Format the combined result into the desired structure
    combined_output = []
    for scope, subscopes in combined_times.items():
        for subcope, times in subscopes.items():
            total_seconds = (
                time_to_seconds(times['Chargable_Time']) + time_to_seconds(times['Non_Chargable_Time'])
            )
            combined_output.append({
                "date": f"{past_times[0]['date']} , {current_times[0]['date']}",
                "nature_of_scope": scope,
                "SubScope": subcope,
                'Chargable_Time': times['Chargable_Time'],
                'Non_Chargable_Time': times['Non_Chargable_Time'],
                'Total_Time_Taken': seconds_to_time(total_seconds)
            })
   
    return combined_output




# --------------------------------scopecumsubcope_total_taken



—------------------------------------


#-------------------------------------------subscopewisetimetaken------------------
#--------------------------------------past funtion------------------
def pastdate_userwise_report11(db: Session, picked_date: str, to_date: str) -> dict:
    '''subscope wise timetaken'''
    picked_datett = datetime.strptime(picked_date, "%Y-%m-%d")
    to_datett = datetime.strptime(to_date, "%Y-%m-%d")


    daily_summaries = []  # Changed to a list to hold each day's summaries
    current_day = picked_datett


    while current_day <= to_datett:
        user_times = defaultdict(lambda: defaultdict(lambda: defaultdict(lambda: defaultdict(dict))))


        # Query total time taken for the current day and join with TL table
        records = db.query(models.TotalTimeTaken).join(
            models.TL, models.TotalTimeTaken.service_id == models.TL.Service_ID
        ).filter(
            models.TotalTimeTaken.date == current_day.date()
        ).all()


        # Process the records
        for record in records:
            # Fetch username from the User_table
            username = db.query(models.User_table.username).filter(
                models.User_table.user_id == record.user_id
            ).scalar() or "Unknown"


            service_id = record.service_id
           
            # Fetch additional fields from TL
            tl_record = db.query(models.TL).filter(models.TL.Service_ID == service_id).first()
   
            chargable_time = "00:00:00"
            non_chargable_time = "00:00:00"
            entity = None


            if tl_record:
                entity = tl_record.name_of_entity  # Assuming this is directly from TL


                scope = db.query(models.scope).filter(models.scope.scope_id == tl_record.Scope).first()
                subscope = db.query(models.sub_scope).filter(models.sub_scope.sub_scope_id == tl_record.From).first()


                # Determine Chargable_Time based on type of activity
                if tl_record.type_of_activity == "CHARGABLE":
                    chargable_time = record.total_inprogress_time or "00:00:00"
                elif tl_record.type_of_activity == "Non-Charchable":
                    non_chargable_time = record.total_inprogress_time or "00:00:00"
               
                # Fetch the scope name
                scope_name = scope.scope if scope else "Unknown"
                subscope_name = subscope.sub_scope if subscope else "unknown"  
            else:
                scope_name = "Unknown"
                subscope_name = "unknown"


            # Function to convert time strings to seconds
            def time_to_seconds(time_str):
                if time_str == "00:00:00":
                    return 0
                hours, minutes, seconds = map(int, time_str.split(':'))
                return hours * 3600 + minutes * 60 + seconds


            # Function to convert seconds back to HH:MM:SS
            def seconds_to_time(seconds):
                hours = seconds // 3600
                minutes = (seconds % 3600) // 60
                seconds = seconds % 60
                return f"{hours:02}:{minutes:02}:{seconds:02}"


            # Aggregate times
            user_times[username][scope_name][subscope_name][service_id] = {
                'in_progress': record.total_inprogress_time or "00:00:00",
                'entity': entity,
                'scope': scope_name,
                'subscope': subscope_name,
                'Chargable_Time': chargable_time,
                'Non_Chargable_Time': non_chargable_time,
                'Total_Time': "00:00:00"  # Initialize Total_Time to zero
            }


        # Aggregate the totals for each user, scope, and subscope
        for username, scopes in user_times.items():
            for scope_name, subscopes in scopes.items():
                for subscope_name, services in subscopes.items():
                    total_chargable_seconds = 0
                    total_non_chargable_seconds = 0


                    for service_id, times in services.items():
                        total_chargable_seconds += time_to_seconds(times['Chargable_Time'])
                        total_non_chargable_seconds += time_to_seconds(times['Non_Chargable_Time'])
                        # Update the in_progress and entity if needed
                        user_times[username][scope_name][subscope_name][service_id]['Total_Time'] = times['Total_Time']


                    # Set aggregated Chargable and Non-Chargable Time
                    aggregated_chargable_time = seconds_to_time(total_chargable_seconds)
                    aggregated_non_chargable_time = seconds_to_time(total_non_chargable_seconds)


                    # Update the first entry for the subscope with aggregated times
                    user_times[username][scope_name][subscope_name]['Chargable_Time'] = aggregated_chargable_time
                    user_times[username][scope_name][subscope_name]['Non_Chargable_Time'] = aggregated_non_chargable_time
                    user_times[username][scope_name][subscope_name]['Total_Time'] = seconds_to_time(total_chargable_seconds + total_non_chargable_seconds)


        # Only add the summary if there was data for the day
        if user_times:
            for username, scopes in user_times.items():
                for scope_name, subscopes in scopes.items():
                    for subscope_name, services in subscopes.items():
                        formatted_day_summary = {
                            "date": current_day.strftime("%Y-%m-%d"),  # Date as a key-value pair
                            "nature_of_scope": scope_name,
                            "subscope": subscope_name,
                            'Chargable_Time': user_times[username][scope_name][subscope_name]['Chargable_Time'],
                            'Non_Chargable_Time': user_times[username][scope_name][subscope_name]['Non_Chargable_Time'],
                            'Total_Time': user_times[username][scope_name][subscope_name]['Total_Time'],  # Fetch Total_Time from user_times
                        }


                        daily_summaries.append(formatted_day_summary)  # Add each entry to the list


        current_day += timedelta(days=1)


    return daily_summaries
#-----------------------current function------------------------------


def calculate_end_time_for_user11(db: Session, picked_date: str, to_date: str) -> dict:
    '''subscope wise time taken'''
    picked_datett = datetime.strptime(picked_date, "%Y-%m-%d")
    to_datett = datetime.strptime(to_date, "%Y-%m-%d")
    current_time = datetime.now()  # For ongoing activities


    def process_records_for_day(date, activity, records, start_field, end_field, user_field, user_times):
        has_activity_for_day = False  # Track if any valid data exists for the day


        for record in records:
            start_time = getattr(record, start_field)
            end_time = getattr(record, end_field) or current_time  # Use current_time if ongoing


            # Ensure the record falls exactly on the specified date
            if start_time.date() != date:
                continue


            time_diff = end_time - start_time
            has_activity_for_day = True  # Mark that valid data exists


            # Fetch user from User_table
            user = db.query(models.User_table).filter(
                models.User_table.user_id == getattr(record, user_field)
            ).first()
           
            # Construct the username from firstname and lastname
            if user:
                username = f"{user.firstname} {user.lastname}"  # Concatenate firstname and lastname
            else:
                username = "Unknown"


            service_id = getattr(record, 'Service_ID')


            # Fetch TL record for work status and metadata, including entity, scope, subscope, and type_of_activity
            tl_record = db.query(models.TL).filter(
                models.TL.Service_ID == service_id
            ).first()


            # Get the entity name, work status, scope, subscope, and type_of_activity
            entity_name = tl_record.name_of_entity if tl_record else "Unknown Entity"
            scope = tl_record.Scope if tl_record else "N/A"
            subscope = tl_record.From if tl_record else "Unknown Subscope"
            type_of_activity = tl_record.type_of_activity if tl_record else "Unknown"


            # Determine whether the time is chargeable or non-chargeable based on type_of_activity
            if type_of_activity == "CHARGABLE":
                chargeable_time = time_diff
                non_chargeable_time = timedelta(0)
            elif type_of_activity == "Non-Charchable":
                chargeable_time = timedelta(0)
                non_chargeable_time = time_diff
            else:
                chargeable_time = timedelta(0)
                non_chargeable_time = timedelta(0)


            # Accumulate time for each activity
            if (username, entity_name, scope, subscope) not in user_times:
                user_times[(username, entity_name, scope, subscope)] = defaultdict(lambda: defaultdict(timedelta))


            user_times[(username, entity_name, scope, subscope)][service_id]['Chargable_Time'] += chargeable_time
            user_times[(username, entity_name, scope, subscope)][service_id]['Non_Chargable_Time'] += non_chargeable_time


            # Store scope and subscope for the user
            if tl_record:
                user_times[(username, entity_name, scope, subscope)][service_id].update({
                    'scope': str(scope),
                    'subscope': str(subscope),
                })


        return has_activity_for_day  # Return whether any activity was processed for the day


    # Main function that generates the daily summaries
    daily_summaries = []


    current_day = picked_datett


    while current_day <= to_datett:
        user_times = defaultdict(lambda: defaultdict(lambda: defaultdict(timedelta)))


        # Track if any activities were processed for the current day
        day_has_data = False


        # Process each activity type
        for activity, model, start_field, end_field in [
            ('in_progress', models.INPROGRESS, 'start_time', 'end_time'),
        ]:
            records = db.query(model).filter(
                getattr(model, start_field).between(
                    current_day.replace(hour=0, minute=0, second=0),
                    current_day.replace(hour=23, minute=59, second=59)
                )
            ).all()


            # Process records and check if there was any valid data
            if process_records_for_day(current_day.date(), activity, records, start_field, end_field, 'user_id', user_times):
                day_has_data = True


        # Only add the summary if there was data for the day
        if day_has_data:
            for (username, entity_name, scope, subscope) in user_times:
                for service_id in user_times[(username, entity_name, scope, subscope)]:
                    formatted_day_summary = {
                        'date': current_day.strftime("%Y-%m-%d"),  # Add date as a field
                        'Nature_of_Scope': user_times[(username, entity_name, scope, subscope)][service_id]['scope'],
                        'SubScope': user_times[(username, entity_name, scope, subscope)][service_id]['subscope'],
                        'Chargable_Time': format_timedelta_to_str(user_times[(username, entity_name, scope, subscope)][service_id]['Chargable_Time']),
                        'Non_Chargable_Time': format_timedelta_to_str(user_times[(username, entity_name, scope, subscope)][service_id]['Non_Chargable_Time']),
                        'total_time_take': format_timedelta_to_str(
                            user_times[(username, entity_name, scope, subscope)][service_id]['Chargable_Time'] +
                            user_times[(username, entity_name, scope, subscope)][service_id]['Non_Chargable_Time']
                        ),
                    }
                    daily_summaries.append(formatted_day_summary)  # Append to the list


        current_day += timedelta(days=1)


    return daily_summaries




def combine_subscopeswise_times(past_times, current_times):
    """Combine past and current times for matching Nature of Scope."""
    combined_times = defaultdict(lambda: defaultdict(lambda: {'Chargable_Time': "00:00:00", 'Non_Chargable_Time': "00:00:00"}))


    def time_to_seconds(time_str):
        """Convert HH:MM:SS string to seconds."""
        hours, minutes, seconds = map(int, time_str.split(':'))
        return hours * 3600 + minutes * 60 + seconds


    def seconds_to_time(seconds):
        """Convert seconds to HH:MM:SS string."""
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        seconds = seconds % 60
        return f"{hours:02}:{minutes:02}:{seconds:02}"


    # Combine times from past and current records
    for times in past_times + current_times:
        subscope = times['SubScope']  


        combined_times[subscope]['Chargable_Time'] = seconds_to_time(
            time_to_seconds(combined_times[subscope]['Chargable_Time']) +
            time_to_seconds(times['Chargable_Time'])
        )


        combined_times[subscope]['Non_Chargable_Time'] = seconds_to_time(
            time_to_seconds(combined_times[subscope]['Non_Chargable_Time']) +
            time_to_seconds(times['Non_Chargable_Time'])
        )


    # Format the final combined results into a list for easy viewing or reporting
    combined_results = []
    for scope, subscopes in combined_times.items():
        for subscope, time_data in subscopes.items():
            combined_results.append({
                'Nature_of_Scope': scope,
                'SubScope': subscope,
                'Chargable_Time': time_data['Chargable_Time'],
                'Non_Chargable_Time': time_data['Non_Chargable_Time'],
                'Total_Time': seconds_to_time(
                    time_to_seconds(time_data['Chargable_Time']) + time_to_seconds(time_data['Non_Chargable_Time'])
                )
            })


    return combined_results


#-------------------------------------------subscopewisetimetaken------------------


main.py

   elif picked_date_obj < current_date and to_date_obj == current_date:
        past_times = crud.pastdate_userwise_report11(db, picked_date, picked_date)
        current_times = crud.calculate_end_time_for_user11(db, str(to_date_obj), str(to_date_obj))
        total_times = crud.combine_subscopeswise_times(past_times, current_times)


—-------------------


from collections import defaultdict


def combine_subscopeswisenature_times(past_times, current_times):
    """Combine past and current times for matching Nature of Scope and SubScope."""
    combined_times = defaultdict(lambda: defaultdict(lambda: defaultdict(lambda: {'Chargable_Time': "00:00:00", 'Non_Chargable_Time': "00:00:00", 'Count': 0})))


    def time_to_seconds(time_str):
        """Convert HH:MM:SS string to seconds."""
        hours, minutes, seconds = map(int, time_str.split(':'))
        return hours * 3600 + minutes * 60 + seconds


    def seconds_to_time(seconds):
        """Convert seconds to HH:MM:SS string."""
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        seconds = seconds % 60
        return f"{hours:02}:{minutes:02}:{seconds:02}"


    # Combine times from past and current records
    for times in past_times + current_times:
        nature_of_scope = times['Nature_of_Scope']
        subscope = times['SubScope']
        nature_of_work = times['nature_of_work']
       
        # Combine times for matching Nature_of_Scope, SubScope, and nature_of_work
        combined_times[nature_of_scope][subscope][nature_of_work]['Chargable_Time'] = seconds_to_time(
            time_to_seconds(combined_times[nature_of_scope][subscope][nature_of_work]['Chargable_Time']) +
            time_to_seconds(times['Chargable_Time'])
        )


        combined_times[nature_of_scope][subscope][nature_of_work]['Non_Chargable_Time'] = seconds_to_time(
            time_to_seconds(combined_times[nature_of_scope][subscope][nature_of_work]['Non_Chargable_Time']) +
            time_to_seconds(times['Non_Chargable_Time'])
        )


        # Update the Count for matching Nature_of_Scope, SubScope, and nature_of_work
        # print(f"Processing record: {times}")
        combined_times[nature_of_scope][subscope][nature_of_work]['Count'] = int(times['Count'])


    # Format the final combined results into a list for easy viewing or reporting
    combined_results = []
    for nature_of_scope, subscopes in combined_times.items():
        for subscope, work_data in subscopes.items():
            for nature_of_work, time_data in work_data.items():
                total_chargable_seconds = time_to_seconds(time_data['Chargable_Time'])
                total_non_chargable_seconds = time_to_seconds(time_data['Non_Chargable_Time'])
                total_time_taken = seconds_to_time(total_chargable_seconds + total_non_chargable_seconds)
               
                combined_results.append({
                    'date': f"{past_times[0]['date']},{current_times[0]['date']}",
                    'Nature_of_Scope': nature_of_scope,
                    'SubScope': subscope,
                    'nature_of_work': nature_of_work,
                    'Chargable_Time': time_data['Chargable_Time'],
                    'Non_Chargable_Time': time_data['Non_Chargable_Time'],
                    'total_time_taken': total_time_taken,
                    'Count': time_data['Count'],
                })


    return combined_results


# -----------start
from datetime import datetime, date
from typing import List


@app.post("/subcope_cum_natureofwork_time_taken", response_model=List[dict])
def get_total_time(
    picked_date: Annotated[str, Form()],
    to_date: Annotated[str, Form()],
    db: Session = Depends(get_db)
):
    # Convert strings to date objects
    picked_date_obj = datetime.strptime(picked_date, "%Y-%m-%d").date()
    to_date_obj = datetime.strptime(to_date, "%Y-%m-%d").date()
    current_date = date.today()  # Get the current date without time


    total_times = []


    # Check if both picked_date and to_date are less than current date
    if to_date_obj < current_date and picked_date_obj < current_date:
        total_times = crud.pastdate_userwise_report12(db, picked_date, to_date)


    # Check if both picked_date and to_date are equal to current date
    elif to_date_obj == current_date and picked_date_obj == current_date:
        total_times = crud.calculate_end_time_for_user12(db, picked_date, to_date)


    elif picked_date_obj < current_date and to_date_obj == current_date:
        past_times = crud.pastdate_userwise_report12(db, picked_date, picked_date)
        current_times = crud.calculate_end_time_for_user12(db, str(to_date_obj), str(to_date_obj))
        total_times = crud.combine_subscopeswisenature_times(past_times, current_times)
       
    return total_times


# ----------------------end


—-------------------------


def insert_user(
   db:Session,username:str,role:str,firstname:str,lastname:str,location:str
):
   
    active_user = db.query(models.User_table).filter(
        models.User_table.username == username,
        models.User_table.user_status == 1
    ).first()


   
    if active_user:
        return "User already exists"


 
    inactive_user = db.query(models.User_table).filter(
        models.User_table.username == username,
        models.User_table.user_status == 0
    ).first()


    if inactive_user:
        inactive_user.user_status = 1  
        inactive_user.role = role
        inactive_user.firstname = firstname
        inactive_user.lastname = lastname
        inactive_user.location = location
       
        db.commit()
        return "Success"


   
    db_insert_user = models.User_table(
       username = username,role=role,firstname = firstname,lastname = lastname,location=location
    )


    db.add(db_insert_user)


    try:
        db.commit()
        return "Success"
    except Exception as e:
        db.rollback()
        return "Failure"

