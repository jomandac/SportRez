from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from database import get_db, init_db, hash_lozinka
import os

app = Flask(__name__)
CORS(app)

init_db()

@app.route('/')
def index():
    return send_from_directory('.', 'sportski-termini.html')

@app.route('/admin')
def admin_page():
    return send_from_directory('.', 'admin.html')

@app.route('/api/tereni', methods=['GET'])
def get_tereni():
    conn = get_db()
    tereni = conn.execute('SELECT * FROM tereni').fetchall()
    conn.close()
    return jsonify([dict(t) for t in tereni])

@app.route('/api/rezervacije', methods=['GET'])
def get_rezervacije():
    teren_id = request.args.get('teren_id')
    datum = request.args.get('datum')
    if not teren_id or not datum:
        return jsonify({'greska': 'Nedostaju parametri'}), 400
    conn = get_db()
    zauzeti = conn.execute('''
        SELECT termin_od, termin_do FROM rezervacije
        WHERE teren_id = ? AND datum = ? AND status = 'aktivna'
    ''', (teren_id, datum)).fetchall()
    conn.close()
    return jsonify([dict(z) for z in zauzeti])

@app.route('/api/rezervacije', methods=['POST'])
def nova_rezervacija():
    podaci = request.get_json()

    teren_id    = podaci.get('teren_id')
    datum       = podaci.get('datum')
    termin_od   = podaci.get('termin_od')
    termin_do   = podaci.get('termin_do')
    ime         = podaci.get('ime')
    email       = podaci.get('email')
    telefon     = podaci.get('telefon')
    korisnik_id = podaci.get('korisnik_id')

    if not all([teren_id, datum, termin_od, termin_do, ime, email]):
        return jsonify({'greska': 'Ispunite sve obavezne podatke'}), 400

    from datetime import date, datetime
    danas = date.today()
    odabrani = datetime.strptime(datum, '%Y-%m-%d').date()
    if odabrani < danas:
        return jsonify({'greska': 'Ne možete rezervirati termin u prošlosti'}), 400
    if odabrani == danas:
        sada = datetime.now().strftime('%H:%M')
        if termin_od <= sada:
            return jsonify({'greska': 'Taj termin je već prošao danas'}), 400

    if not korisnik_id:
        return jsonify({'greska': 'Morate biti prijavljeni za rezervaciju'}), 401

    conn_check = get_db()
    korisnik = conn_check.execute('SELECT id FROM korisnici WHERE id = ?', (korisnik_id,)).fetchone()
    conn_check.close()
    if not korisnik:
        return jsonify({'greska': 'Korisnički račun ne postoji'}), 401


    try:
        conn = get_db()

       
        postojeca = conn.execute('''
            SELECT id FROM rezervacije
            WHERE teren_id = ? AND datum = ? AND termin_od = ? AND status = 'aktivna'
        ''', (teren_id, datum, termin_od)).fetchone()

        if postojeca:
            conn.close()
            return jsonify({'greska': 'Taj termin je već zauzet'}), 409

        cursor = conn.execute('''
            INSERT INTO rezervacije
            (korisnik_id, teren_id, datum, termin_od, termin_do, ime, email, telefon, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'aktivna')
        ''', (korisnik_id, teren_id, datum, termin_od, termin_do, ime, email, telefon or None))
        conn.commit()
        rezervacija_id = cursor.lastrowid
        conn.close()
        return jsonify({'uspjeh': True, 'id': rezervacija_id})
    except Exception as e:
        print('GREŠKA REZERVACIJA:', str(e))
        return jsonify({'greska': 'Greška na serveru: ' + str(e)}), 500



@app.route('/api/registracija', methods=['POST'])
def registracija():
    podaci = request.get_json()
    ime     = podaci.get('ime')
    prezime = podaci.get('prezime')
    email   = podaci.get('email')
    telefon = podaci.get('telefon')
    lozinka = podaci.get('lozinka')

    if not all([ime, email, lozinka]):
        return jsonify({'greska': 'Nedostaju podaci'}), 400

    try:
        conn = get_db()
        cursor = conn.execute('''
            INSERT INTO korisnici (ime, prezime, email, telefon, lozinka)
            VALUES (?, ?, ?, ?, ?)
        ''', (ime, prezime or '', email, telefon or None, hash_lozinka(lozinka)))
        conn.commit()
        korisnik_id = cursor.lastrowid
        conn.close()
        return jsonify({'uspjeh': True, 'id': korisnik_id, 'ime': ime, 'email': email})
    except Exception as e:
        print('GREŠKA REGISTRACIJA:', str(e))
        if 'UNIQUE' in str(e):
            return jsonify({'greska': 'E-mail već postoji'}), 409
        return jsonify({'greska': 'Greška na serveru: ' + str(e)}), 500

@app.route('/api/prijava', methods=['POST'])
def prijava():
    podaci  = request.get_json()
    email   = podaci.get('email')
    lozinka = podaci.get('lozinka')

    conn = get_db()
    korisnik = conn.execute(
        'SELECT * FROM korisnici WHERE email = ?', (email,)
    ).fetchone()
    conn.close()

    if not korisnik or korisnik['lozinka'] != hash_lozinka(lozinka):
        return jsonify({'greska': 'Pogrešan e-mail ili lozinka'}), 401

    return jsonify({
        'uspjeh': True,
        'korisnik': {
            'id':      korisnik['id'],
            'ime':     korisnik['ime'],
            'prezime': korisnik['prezime'],
            'email':   korisnik['email']
        }
    })



@app.route('/api/moje-rezervacije/<int:korisnik_id>', methods=['GET'])
def moje_rezervacije(korisnik_id):
    conn = get_db()
    rezervacije = conn.execute('''
        SELECT r.*, t.naziv as teren_naziv, t.sport as teren_sport, t.lokacija as teren_lokacija, t.cijena as teren_cijena
        FROM rezervacije r
        LEFT JOIN tereni t ON r.teren_id = t.id
        WHERE r.korisnik_id = ?
        ORDER BY r.datum DESC, r.termin_od DESC
    ''', (korisnik_id,)).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rezervacije])

@app.route('/api/moje-rezervacije/<int:rez_id>/otkazi', methods=['PUT'])
def otkazi_rezervaciju(rez_id):
    from datetime import date, datetime
    conn = get_db()
    rez = conn.execute('SELECT * FROM rezervacije WHERE id = ?', (rez_id,)).fetchone()
    if not rez:
        conn.close()
        return jsonify({'greska': 'Rezervacija ne postoji'}), 404

    rez_datum = datetime.strptime(rez['datum'], '%Y-%m-%d').date()
    danas = date.today()
    if rez_datum < danas:
        conn.close()
        return jsonify({'greska': 'Ne možete otkazati prošlu rezervaciju'}), 400
    if rez_datum == danas:
        sada = datetime.now().strftime('%H:%M')
        if rez['termin_od'] <= sada:
            conn.close()
            return jsonify({'greska': 'Ne možete otkazati termin koji je već prošao'}), 400

    conn.execute("UPDATE rezervacije SET status = 'otkazana' WHERE id = ?", (rez_id,))
    conn.commit()
    conn.close()
    return jsonify({'uspjeh': True})



@app.route('/api/admin/prijava', methods=['POST'])
def admin_prijava():
    podaci = request.get_json()
    email = podaci.get('email')
    lozinka = podaci.get('lozinka')

    conn = get_db()
    korisnik = conn.execute(
        "SELECT * FROM korisnici WHERE email = ? AND uloga = 'admin'", (email,)
    ).fetchone()
    conn.close()

    if not korisnik or korisnik['lozinka'] != hash_lozinka(lozinka):
        return jsonify({'greska': 'Pogrešni podaci ili nemate admin pristup'}), 401

    return jsonify({
        'uspjeh': True,
        'admin': {
            'id': korisnik['id'],
            'ime': korisnik['ime'],
            'email': korisnik['email']
        }
    })


@app.route('/api/admin/korisnici', methods=['GET'])
def admin_get_korisnici():
    conn = get_db()
    korisnici = conn.execute('SELECT id, ime, prezime, email, telefon, uloga, created_at FROM korisnici ORDER BY id DESC').fetchall()
    conn.close()
    return jsonify([dict(k) for k in korisnici])

@app.route('/api/admin/korisnici', methods=['POST'])
def admin_create_korisnik():
    podaci = request.get_json()
    ime = podaci.get('ime')
    prezime = podaci.get('prezime', '')
    email = podaci.get('email')
    telefon = podaci.get('telefon')
    lozinka = podaci.get('lozinka')
    uloga = podaci.get('uloga', 'korisnik')

    if not all([ime, email, lozinka]):
        return jsonify({'greska': 'Nedostaju obavezni podaci'}), 400

    try:
        conn = get_db()
        conn.execute('''
            INSERT INTO korisnici (ime, prezime, email, telefon, lozinka, uloga)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (ime, prezime, email, telefon or None, hash_lozinka(lozinka), uloga))
        conn.commit()
        conn.close()
        return jsonify({'uspjeh': True})
    except Exception as e:
        if 'UNIQUE' in str(e):
            return jsonify({'greska': 'E-mail već postoji'}), 409
        return jsonify({'greska': str(e)}), 500

@app.route('/api/admin/korisnici/<int:id>', methods=['PUT'])
def admin_update_korisnik(id):
    podaci = request.get_json()
    conn = get_db()
    fields = []
    values = []
    for key in ['ime', 'prezime', 'email', 'telefon', 'uloga']:
        if key in podaci:
            fields.append(f'{key} = ?')
            values.append(podaci[key])
    if 'lozinka' in podaci and podaci['lozinka']:
        fields.append('lozinka = ?')
        values.append(hash_lozinka(podaci['lozinka']))
    if not fields:
        conn.close()
        return jsonify({'greska': 'Nema podataka za ažuriranje'}), 400
    values.append(id)
    try:
        conn.execute(f"UPDATE korisnici SET {', '.join(fields)} WHERE id = ?", values)
        conn.commit()
        conn.close()
        return jsonify({'uspjeh': True})
    except Exception as e:
        conn.close()
        if 'UNIQUE' in str(e):
            return jsonify({'greska': 'E-mail već postoji'}), 409
        return jsonify({'greska': str(e)}), 500

@app.route('/api/admin/korisnici/<int:id>', methods=['DELETE'])
def admin_delete_korisnik(id):
    conn = get_db()
    conn.execute('DELETE FROM rezervacije WHERE korisnik_id = ?', (id,))
    conn.execute('DELETE FROM korisnici WHERE id = ?', (id,))

    conn.commit()
    conn.close()
    return jsonify({'uspjeh': True})

@app.route('/api/admin/tereni', methods=['GET'])
def admin_get_tereni():
    conn = get_db()
    tereni = conn.execute('SELECT * FROM tereni ORDER BY id DESC').fetchall()
    conn.close()
    return jsonify([dict(t) for t in tereni])

@app.route('/api/admin/tereni', methods=['POST'])
def admin_create_teren():
    podaci = request.get_json()
    naziv = podaci.get('naziv')
    sport = podaci.get('sport')
    lokacija = podaci.get('lokacija', '')
    cijena = podaci.get('cijena')
    opis = podaci.get('opis', '')

    if not all([naziv, sport, cijena]):
        return jsonify({'greska': 'Nedostaju obavezni podaci'}), 400

    try:
        conn = get_db()
        conn.execute('''
            INSERT INTO tereni (naziv, sport, lokacija, cijena, opis)
            VALUES (?, ?, ?, ?, ?)
        ''', (naziv, sport, lokacija, cijena, opis))
        conn.commit()
        conn.close()
        return jsonify({'uspjeh': True})
    except Exception as e:
        return jsonify({'greska': str(e)}), 500

@app.route('/api/admin/tereni/<int:id>', methods=['PUT'])
def admin_update_teren(id):
    podaci = request.get_json()
    conn = get_db()
    fields = []
    values = []
    for key in ['naziv', 'sport', 'lokacija', 'cijena', 'opis']:
        if key in podaci:
            fields.append(f'{key} = ?')
            values.append(podaci[key])
    if not fields:
        conn.close()
        return jsonify({'greska': 'Nema podataka za ažuriranje'}), 400
    values.append(id)
    conn.execute(f"UPDATE tereni SET {', '.join(fields)} WHERE id = ?", values)
    conn.commit()
    conn.close()
    return jsonify({'uspjeh': True})

@app.route('/api/admin/tereni/<int:id>', methods=['DELETE'])
def admin_delete_teren(id):
    conn = get_db()
    conn.execute('DELETE FROM tereni WHERE id = ?', (id,))
    conn.commit()
    conn.close()
    return jsonify({'uspjeh': True})


@app.route('/api/admin/rezervacije', methods=['GET'])
def admin_get_rezervacije():
    conn = get_db()
    rezervacije = conn.execute('''
        SELECT r.*, t.naziv as teren_naziv, t.sport as teren_sport
        FROM rezervacije r
        LEFT JOIN tereni t ON r.teren_id = t.id
        ORDER BY r.id DESC
    ''').fetchall()
    conn.close()
    return jsonify([dict(r) for r in rezervacije])

@app.route('/api/admin/rezervacije/<int:id>', methods=['PUT'])
def admin_update_rezervacija(id):
    podaci = request.get_json()
    conn = get_db()
    fields = []
    values = []
    for key in ['datum', 'termin_od', 'termin_do', 'ime', 'email', 'telefon', 'status', 'teren_id']:
        if key in podaci:
            fields.append(f'{key} = ?')
            values.append(podaci[key])
    if not fields:
        conn.close()
        return jsonify({'greska': 'Nema podataka za ažuriranje'}), 400
    trenutna = conn.execute('SELECT teren_id, datum, termin_od FROM rezervacije WHERE id = ?', (id,)).fetchone()
    provjeri_teren_id  = podaci.get('teren_id')  or trenutna['teren_id']
    provjeri_datum     = podaci.get('datum')     or trenutna['datum']
    provjeri_termin_od = podaci.get('termin_od') or trenutna['termin_od']

    postojeca = conn.execute('''
        SELECT id FROM rezervacije
        WHERE teren_id = ? AND datum = ? AND termin_od = ? AND status = 'aktivna' AND id != ?
    ''', (provjeri_teren_id, provjeri_datum, provjeri_termin_od, int(id))).fetchone()
    if postojeca:
        conn.close()
        return jsonify({'greska': 'Taj termin je već zauzet'}), 409
    values.append(id)
    conn.execute(f"UPDATE rezervacije SET {', '.join(fields)} WHERE id = ?", values)
    conn.commit()
    conn.close()
    return jsonify({'uspjeh': True})

@app.route('/api/admin/rezervacije/<int:id>', methods=['DELETE'])
def admin_delete_rezervacija(id):
    conn = get_db()
    conn.execute('DELETE FROM rezervacije WHERE id = ?', (id,))
    conn.commit()
    conn.close()
    return jsonify({'uspjeh': True})


@app.route('/api/admin/statistike', methods=['GET'])
def admin_statistike():
    conn = get_db()
    korisnici = conn.execute('SELECT COUNT(*) FROM korisnici').fetchone()[0]
    tereni = conn.execute('SELECT COUNT(*) FROM tereni').fetchone()[0]
    rezervacije = conn.execute('SELECT COUNT(*) FROM rezervacije').fetchone()[0]
    aktivne = conn.execute("SELECT COUNT(*) FROM rezervacije WHERE status = 'aktivna'").fetchone()[0]
    conn.close()
    return jsonify({
        'korisnici': korisnici,
        'tereni': tereni,
        'rezervacije': rezervacije,
        'aktivne_rezervacije': aktivne
    })

if __name__ == '__main__':
    app.run(debug=False, port=int(os.environ.get('PORT', 5000)), host='0.0.0.0')